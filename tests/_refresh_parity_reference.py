#!/usr/bin/env python3
"""Refresh the Perl-derived parity reference fixtures (one-off, manual).

Run from the inner repo against any working Perl Genesis2 install:

    python tests/_refresh_parity_reference.py --genesis-home /path/to/Genesis2

For each in-scope demo this script:

1. Stages the Perl demo from ``<genesis-home>/demo/<name>`` into a tmp
   workdir and runs ``make gen`` against the supplied Genesis2.
2. Walks the emitted Verilog, applies ``_parity_normalize.normalize`` and
   groups distinct normalised bodies per base module.
3. Writes one normalised ``.v`` per ``(base, body)`` pair under
   ``tests/fixtures/parity_reference/<demo>/`` plus an ``index.tsv``
   recording representative ``(base, sig)`` pairs and a top-level
   ``PROVENANCE.txt`` with the Genesis2 git SHA, dirty flag, paths and
   timestamp.
4. As a one-time integrity check, runs the same demo through genesispy's
   Python API (the path the smoke test uses) and asserts the per-base
   normalised body sets match Perl. Catches argv mismatches between the
   Makefile and the API.

Underscore prefix keeps pytest from collecting this module.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

# Make the sibling helper importable when run as a script.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from _parity_normalize import build_variant_map, normalize, parse_header  # noqa: E402

INNER_REPO = _HERE.parent
DEMOS_DIR = INNER_REPO / "demos"
FIXTURES = _HERE / "fixtures" / "parity_reference"

# Per-demo extra `genesispy` flags for the API-side cross-check, mirroring
# the EXTRA_MAKE_ARGS table in test_parity/test_perl_parity.py. Perl's
# Makefile default uses XML_CONFIG=config.xml for many_iterative_wallace_trees;
# genesispy default is no config (different widths). Force the JSON
# equivalent (config.json is committed alongside config.xml in the demo).
PY_API_EXTRA: Dict[str, List[str]] = {
    "many_iterative_wallace_trees": ["--json", "config.json"],
}

# Per-demo argv for the genesispy API call. Mirrors the per-demo Makefile
# in genesispy/demos/<name>/Makefile (TOP and INPUTS).
PY_API_ARGS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "regfile": (
        "top",
        ("top.vpy", "reg_file.vpy", "flop.vpy", "cfg_ifc.vpy", "top_flop_only.vpy"),
    ),
    "iterative_wallace_tree": ("top", ("top.vpy", "wallace.vpy", "CSA.vpy")),
    "many_iterative_wallace_trees": ("top", ("top.vpy", "wallace.vpy", "CSA.vpy")),
    "random_logic": ("top", ("top.vpy", "OneHotMux.vpy")),
}

# Per-demo missing-source files to create as empty stubs in the staged Perl
# tree, mirroring test_parity/test_perl_parity.py::PERL_MISSING_SOURCES.
# Genesis2's random_logic Makefile lists ROM.vp in GENESIS_DESIGN but the
# file is not in the submodule; an empty ROM.vp satisfies make's dependency
# and Genesis2 parses it as a no-op.
PERL_MISSING_SOURCES: Dict[str, List[str]] = {
    "random_logic": ["genesis-source/ROM.vp"],
}

DEMOS = (
    "regfile",
    "iterative_wallace_tree",
    "many_iterative_wallace_trees",
    "random_logic",
)

PERL_OUT_SUBDIRS = ("genesis_verif", "genesis_synth")
PY_OUT_SUBDIRS = ("genesis_synth", "genesis_verif")

# Build artefacts left in a live demo dir that confuse `make gen` if copied.
_STALE_NAMES = {
    "genesis_synth", "genesis_verif", "genesis_raw", "genesis_work",
    "obj_dir", "xcelium.d", "xrun.history", "xrun.log",
    "genesis_vlog.vf", "genesis_vlog.synth.vf", "genesis_vlog.verif.vf",
    "depend.list", "wallace.xml", "small_wallace.xml", "tiny_wallace.xml",
    "genesis.log", "genesis_clean.cmd",
}


def _ignore_stale(_dir: str, names: List[str]) -> List[str]:
    return [n for n in names if n in _STALE_NAMES]


def _build_env(genesis_home: Path) -> Dict[str, str]:
    env = os.environ.copy()
    env["GENESIS_HOME"] = str(genesis_home)
    perl_libs = [
        str(genesis_home / "PerlLibs"),
        str(genesis_home / "PerlLibs" / "ExtrasForOldPerlDistributions"),
    ]
    if env.get("PERL5LIB"):
        perl_libs.append(env["PERL5LIB"])
    env["PERL5LIB"] = ":".join(perl_libs)
    env["PATH"] = f"{genesis_home / 'bin'}{os.pathsep}{env.get('PATH', '')}"
    return env


def _run_make(workdir: Path, env: Dict[str, str]) -> None:
    r = subprocess.run(
        ["make", "gen"], cwd=workdir, env=env,
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"`make gen` failed in {workdir}\n"
            f"STDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
        )


def _collect_bodies(workdir: Path, subdirs: Tuple[str, ...], all_bases: set
                    ) -> List[Tuple[str, tuple, str]]:
    """Return ``[(base, sig, normalised_body), ...]`` for every emitted .v."""
    rows: List[Tuple[str, tuple, str]] = []
    texts: Dict[str, str] = {}
    for sub in subdirs:
        d = workdir / sub
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.v")):
            text = path.read_text()
            try:
                base, sig = parse_header(text)
            except ValueError:
                continue
            rows.append((base, sig, text))
            texts[str(path)] = text
    vmap = build_variant_map(texts, all_bases)
    return [(base, sig, normalize(text, all_bases, vmap)) for base, sig, text in rows]


def _bases_only(workdir: Path, subdirs: Tuple[str, ...]) -> set:
    bases: set = set()
    for sub in subdirs:
        d = workdir / sub
        if not d.is_dir():
            continue
        for path in d.glob("*.v"):
            try:
                base, _ = parse_header(path.read_text())
            except ValueError:
                continue
            bases.add(base)
    return bases


def _stage_perl(tmp: Path, demo: str, genesis_home: Path) -> Path:
    src = genesis_home / "demo" / demo
    if not src.is_dir():
        raise FileNotFoundError(
            f"Perl demo not found: {src}. Is --genesis-home pointing at a "
            f"Genesis2 install with demo/{demo}/?"
        )
    dst = tmp / "perl"
    shutil.copytree(src, dst, ignore=_ignore_stale)
    for rel in PERL_MISSING_SOURCES.get(demo, []):
        (dst / rel).touch()
    return dst


def _stage_py(tmp: Path, demo: str) -> Path:
    base = tmp / "py"
    base.mkdir()
    shutil.copy(DEMOS_DIR / "genesispy.mk", base / "genesispy.mk")
    dst = base / demo
    shutil.copytree(DEMOS_DIR / demo, dst, ignore=_ignore_stale)
    return dst


def _refresh_demo(demo: str, genesis_home: Path, env: Dict[str, str]) -> None:
    print(f"[{demo}] staging + Perl make gen ...")
    with tempfile.TemporaryDirectory(prefix=f"parity_ref_{demo}_") as tmp_str:
        tmp = Path(tmp_str)
        perl_wd = _stage_perl(tmp, demo, genesis_home)
        _run_make(perl_wd, env)

        # First pass: discover all base names so the normaliser can collapse
        # uniquification suffixes correctly across both sides.
        perl_bases = _bases_only(perl_wd, PERL_OUT_SUBDIRS)

        # genesispy-side cross-check: run via API and compare per-base body
        # sets against Perl. Uses _stage_py + the same demo argv as the
        # smoke test will use.
        py_wd = _stage_py(tmp, demo)
        py_bases = _run_genesispy_api(py_wd, demo)
        all_bases = perl_bases | py_bases

        perl_rows = _collect_bodies(perl_wd, PERL_OUT_SUBDIRS, all_bases)
        py_rows = _collect_bodies(py_wd, PY_OUT_SUBDIRS, all_bases)

        perl_buckets: Dict[str, set] = {}
        for b, _, body in perl_rows:
            perl_buckets.setdefault(b, set()).add(body)
        py_buckets: Dict[str, set] = {}
        for b, _, body in py_rows:
            py_buckets.setdefault(b, set()).add(body)

        if set(perl_buckets) != set(py_buckets):
            raise AssertionError(
                f"[{demo}] base-set mismatch between Perl and genesispy:\n"
                f"  only Perl: {sorted(set(perl_buckets) - set(py_buckets))}\n"
                f"  only Py:   {sorted(set(py_buckets) - set(perl_buckets))}"
            )
        for base in perl_buckets:
            if perl_buckets[base] != py_buckets[base]:
                raise AssertionError(
                    f"[{demo}] base {base!r}: per-base normalised body set "
                    f"differs between Perl and genesispy. Refresh aborted; "
                    f"the Makefile and the smoke-test argv are inconsistent."
                )
        print(f"[{demo}] cross-check OK ({len(perl_buckets)} bases)")

        # Persist Perl bodies (the canonical reference) to the fixture dir.
        out_dir = FIXTURES / demo
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)

        # Pick a representative sig per (base, body). Multiple files may
        # share the same body but have distinct sigs (e.g. regfile reg_file
        # variants); record the lexicographically-first sig as a sample.
        body_sigs: Dict[Tuple[str, str], tuple] = {}
        for base, sig, body in perl_rows:
            key = (base, body)
            cur = body_sigs.get(key)
            if cur is None or repr(sig) < repr(cur):
                body_sigs[key] = sig

        index_lines = ["# filename\tbase\tsig_repr\n"]
        for (base, body), sig in sorted(body_sigs.items(), key=lambda x: (x[0][0], x[0][1])):
            body_hash8 = hashlib.sha256(body.encode()).hexdigest()[:8]
            fname = f"{base}__{body_hash8}.v"
            (out_dir / fname).write_text(body + "\n")
            index_lines.append(f"{fname}\t{base}\t{sig!r}\n")

        (out_dir / "index.tsv").write_text("".join(index_lines))
        print(f"[{demo}] wrote {len(body_sigs)} bodies to {out_dir.relative_to(INNER_REPO)}")


def _run_genesispy_api(workdir: Path, demo: str) -> set:
    """Run genesispy's API on the staged Py workdir; return base set."""
    sys.path.insert(0, str(INNER_REPO / "src"))
    try:
        from genesispy import cache
        from genesispy.cli import parse_args
        from genesispy.manager import Manager
    finally:
        # Keep src on path for the rest of refresh; smoke test won't use this.
        pass

    cache.clear_all()
    top, inputs = PY_API_ARGS[demo]
    argv = []
    for inp in inputs:
        argv.extend(["--input", inp])
    argv.extend(["--top", top, "--srcpath", "genesis_src"])
    argv.extend(PY_API_EXTRA.get(demo, []))

    cwd = os.getcwd()
    os.chdir(workdir)
    try:
        rc = Manager(parse_args(argv)).execute()
        if rc != 0:
            raise RuntimeError(f"[{demo}] genesispy API returned {rc}")
    finally:
        os.chdir(cwd)
    return _bases_only(workdir, PY_OUT_SUBDIRS)


def _git_sha(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"], text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return "<not-a-git-checkout>"


def _git_dirty(path: Path) -> bool:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(path), "status", "--porcelain"], text=True,
        )
        return bool(out.strip())
    except subprocess.CalledProcessError:
        return False


def _write_provenance(genesis_home: Path) -> None:
    now = _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")
    lines = [
        f"refresh_timestamp_utc: {now}",
        f"genesis_home:          {genesis_home}",
        f"genesis2_git_sha:      {_git_sha(genesis_home)}",
        f"genesis2_dirty:        {_git_dirty(genesis_home)}",
        f"inner_repo_git_sha:    {_git_sha(INNER_REPO)}",
        f"inner_repo_dirty:      {_git_dirty(INNER_REPO)}",
        "",
    ]
    (FIXTURES / "PROVENANCE.txt").write_text("\n".join(lines))


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--genesis-home",
        default=os.environ.get("GENESIS_HOME"),
        help="Path to a Perl Genesis2 install (or set $GENESIS_HOME).",
    )
    p.add_argument(
        "--demos", nargs="+", default=list(DEMOS),
        help="Demos to refresh (default: all in-scope).",
    )
    args = p.parse_args(argv)

    if not args.genesis_home:
        p.error("--genesis-home (or $GENESIS_HOME) is required")
    genesis_home = Path(args.genesis_home).resolve()
    if not (genesis_home / "bin" / "Genesis2").is_file():
        p.error(f"{genesis_home}/bin/Genesis2 not found; bad --genesis-home?")

    env = _build_env(genesis_home)
    FIXTURES.mkdir(parents=True, exist_ok=True)

    for demo in args.demos:
        if demo not in PY_API_ARGS:
            p.error(f"unknown demo: {demo}")
        _refresh_demo(demo, genesis_home, env)

    _write_provenance(genesis_home)
    print(f"\nProvenance written to {FIXTURES / 'PROVENANCE.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
