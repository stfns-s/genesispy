"""Staging and toolchain helpers shared by every suite that runs a demo through
``make``: the inner parity smoke/refresh and the outer ``test_parity/`` (which
reaches this module through its ``sys.path`` bridge)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, Optional

try:  # imported as tests._parity_run (inner suite) ...
    from ._stale import ignore_stale
except ImportError:  # ... or as a bare module (refresh script, test_parity bridge)
    from _stale import ignore_stale


def ppi_available() -> bool:
    """True when ``perl`` with the PPI module is on PATH (the vp2vpy helper)."""
    try:
        return subprocess.run(
            ["perl", "-MPPI", "-e", "1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
        ).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_make(
    workdir: Path,
    env: Dict[str, str],
    extra: Optional[Iterable[str]] = None,
    target: str = "gen",
    timeout: int = 180,
) -> None:
    """``make <target> <extra...>`` in ``workdir``; RuntimeError with both
    streams on a non-zero exit."""
    cmd = ["make", target, *(extra or [])]
    r = subprocess.run(
        cmd, cwd=workdir, env=env, capture_output=True, text=True, timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"`{' '.join(cmd)}` failed in {workdir}\n"
            f"STDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
        )


def stage_perl(
    tmp: Path, demo: str, perl_demos: Path, missing_sources: Dict[str, list]
) -> Path:
    """Copy ``perl_demos/<demo>`` into ``tmp/perl`` (stale artefacts dropped)
    and touch the sources its Makefile lists but the checkout lacks."""
    src = perl_demos / demo
    if not src.is_dir():
        raise FileNotFoundError(f"Perl demo not found: {src}")
    dst = tmp / "perl"
    shutil.copytree(src, dst, ignore=ignore_stale)
    for rel in missing_sources.get(demo, []):
        (dst / rel).touch()
    return dst


def stage_py(tmp: Path, demo: str, demos_dir: Path) -> Path:
    """Copy ``demos_dir/<demo>`` into ``tmp/py/<demo>`` beside a copy of the
    shared ``genesispy.mk`` it includes."""
    base = tmp / "py"
    base.mkdir()
    shutil.copy(demos_dir / "genesispy.mk", base / "genesispy.mk")
    dst = base / demo
    shutil.copytree(demos_dir / demo, dst, ignore=ignore_stale)
    return dst
