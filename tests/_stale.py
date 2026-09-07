"""Build artefacts that must not be copied when a live demo dir is staged for a test.

One list for every suite that copies a demo: the inner tests, the parity refresh
script, and ``test_parity/`` through its ``sys.path`` bridge. A copied product
that is newer than the sources makes ``make gen`` skip regeneration, and the
test then asserts against stale files.
"""

from __future__ import annotations

import fnmatch
from typing import Iterable, List

STALE_NAMES = frozenset({
    # genesispy outputs
    "genesis_synth", "genesis_verif", "genesis_raw", "genesis_work", "genesis_synth.j2",
    "genesis_vlog.vf", "genesis_vlog.j2.vf", "genesis_vlog.synth.vf", "genesis_vlog.verif.vf",
    "genesispy_clean.sh", "genesispy.log",
    # Genesis2 (Perl) outputs
    "depend.list", "genesis.log", "genesis_clean.cmd",
    "wallace.xml", "small_wallace.xml", "tiny_wallace.xml",
    "wallace.json", "wallace-small.json", "wallace-tiny.json",
    # dsp demo scratch
    "build", "tmp", "__pycache__",
    # simulator intermediates
    "obj_dir", "xcelium.d", "xrun.history", "xrun.log", "csrc", "simv", "simv.daidir",
    "work", "transcript", "vsim.wlf", "dump.vcd",
})

# shutil.ignore_patterns-style globs.
STALE_PATTERNS = (
    "*.flags", "*.out.v", "*.vvp", "*.vlist", "*.vlist.verif",
    "genesis_synth_ex*", "genesis_vlog_ex*.vf",
)


def is_stale(name: str) -> bool:
    return name in STALE_NAMES or any(fnmatch.fnmatch(name, p) for p in STALE_PATTERNS)


def ignore_stale(_dir: str, names: Iterable[str]) -> List[str]:
    """``shutil.copytree(ignore=...)`` callback."""
    return [n for n in names if is_stale(n)]
