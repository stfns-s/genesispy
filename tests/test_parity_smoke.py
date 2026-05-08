"""Parity smoke test: genesispy output vs frozen Perl-derived reference.

Runs the genesispy pipeline on each in-scope demo and compares its
emitted Verilog (post-normalisation, grouped per base module) to the
checked-in reference under ``fixtures/parity_reference/<demo>/``. The
reference itself is generated one-off by ``_refresh_parity_reference.py``
against a Perl Genesis2 install; this test does not need Perl at runtime.

Comparison is by *set* of normalised module bodies per base, matching the
outer ``test_parity/`` suite. Uniquification suffixes (``_unq<N>`` /
``_KEY_VAL_...``) are folded to ``__U`` so genesispy's post-elaboration
dedup vs Perl's non-deduped output don't register as differences.

A missing reference is a hard failure; refresh per
``doc/genesis2-incompatibilities.md``.
"""

from __future__ import annotations

import difflib
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Tuple

import pytest

from genesispy import cache
from genesispy.cli import parse_args
from genesispy.manager import Manager

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _parity_normalize import normalize, parse_header  # noqa: E402

DEMOS_DIR = Path(__file__).resolve().parents[1] / "demos"
REF_ROOT = Path(__file__).resolve().parent / "fixtures" / "parity_reference"

# Argv per demo, mirroring genesispy/demos/<name>/Makefile and
# _refresh_parity_reference.py:PY_API_ARGS / PY_API_EXTRA.
_DEMO_ARGS: Dict[str, Tuple[str, Tuple[str, ...], Tuple[str, ...]]] = {
    "regfile": (
        "top",
        ("top.vpy", "reg_file.vpy", "flop.vpy", "cfg_ifc.vpy", "top_flop_only.vpy"),
        (),
    ),
    "iterative_wallace_tree": (
        "top", ("top.vpy", "wallace.vpy", "CSA.vpy"), (),
    ),
    "many_iterative_wallace_trees": (
        "top", ("top.vpy", "wallace.vpy", "CSA.vpy"), ("--json", "config.json"),
    ),
    "random_logic": (
        "top", ("top.vpy", "OneHotMux.vpy"), (),
    ),
}


def _stage_demo(tmp: Path, demo: str) -> Path:
    dst = tmp / demo
    shutil.copytree(DEMOS_DIR / demo, dst, dirs_exist_ok=False,
                    ignore=shutil.ignore_patterns(
                        "genesis_synth", "genesis_verif", "genesis_raw"))
    return dst


def _run_genesispy(workdir: Path, demo: str) -> None:
    top, inputs, extra = _DEMO_ARGS[demo]
    argv = []
    for inp in inputs:
        argv.extend(["--input", inp])
    argv.extend(["--top", top, "--srcpath", "genesis_src"])
    argv.extend(extra)

    cache.clear_all()
    cwd = os.getcwd()
    os.chdir(workdir)
    try:
        rc = Manager(parse_args(argv)).execute()
        assert rc == 0, f"genesispy returned {rc} for {demo}"
    finally:
        os.chdir(cwd)


def _collect(workdir: Path) -> Tuple[set, Dict[str, set]]:
    """Return (all_bases, {base: {normalised_body, ...}}) by reading all .v."""
    bases: set = set()
    rows: list[Tuple[str, str]] = []
    for sub in ("genesis_synth", "genesis_verif"):
        d = workdir / sub
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.v")):
            text = path.read_text()
            try:
                base, _ = parse_header(text)
            except ValueError:
                continue
            bases.add(base)
            rows.append((base, text))
    buckets: Dict[str, set] = {}
    for base, text in rows:
        buckets.setdefault(base, set()).add(normalize(text, bases))
    return bases, buckets


def _load_reference(demo: str) -> Tuple[set, Dict[str, set]]:
    ref_dir = REF_ROOT / demo
    index = ref_dir / "index.tsv"
    if not index.is_file():
        pytest.fail(
            f"missing parity reference for {demo!r} at {ref_dir}\n"
            f"refresh with: python tests/_refresh_parity_reference.py "
            f"--genesis-home /path/to/Genesis2"
        )
    bases: set = set()
    buckets: Dict[str, set] = {}
    for line in index.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        fname, base, _sig_repr = line.split("\t", 2)
        body = (ref_dir / fname).read_text().rstrip("\n")
        bases.add(base)
        buckets.setdefault(base, set()).add(body)
    return bases, buckets


@pytest.mark.parametrize("demo", sorted(_DEMO_ARGS))
def test_parity_smoke(tmp_path: Path, demo: str) -> None:
    workdir = _stage_demo(tmp_path, demo)
    _run_genesispy(workdir, demo)
    py_bases, py_buckets = _collect(workdir)

    _ref_bases, ref_buckets = _load_reference(demo)

    if set(py_buckets) != set(ref_buckets):
        only_py = sorted(set(py_buckets) - set(ref_buckets))
        only_ref = sorted(set(ref_buckets) - set(py_buckets))
        pytest.fail(
            f"{demo}: base-set differs from reference\n"
            f"  only in genesispy: {only_py}\n"
            f"  only in reference: {only_ref}"
        )

    failures: list[str] = []
    for base in sorted(ref_buckets):
        py_set = py_buckets[base]
        ref_set = ref_buckets[base]
        if py_set == ref_set:
            continue
        only_py = sorted(py_set - ref_set)
        only_ref = sorted(ref_set - py_set)
        for i, py_body in enumerate(only_py):
            ref_body = only_ref[i] if i < len(only_ref) else ""
            diff = "\n".join(difflib.unified_diff(
                ref_body.splitlines(), py_body.splitlines(),
                fromfile=f"reference:{base}#{i}", tofile=f"genesispy:{base}#{i}",
                n=2, lineterm="",
            ))
            failures.append(f"--- {base} body #{i} ---\n{diff}")
        for i in range(len(only_py), len(only_ref)):
            failures.append(f"{base}: missing genesispy body for reference #{i}")

    if failures:
        pytest.fail(f"{demo}: per-base body mismatch\n" + "\n".join(failures))
