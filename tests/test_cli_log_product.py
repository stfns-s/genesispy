"""Cluster J: CLI flag semantics for --log lazy default and
--product / --vf-out triple-file Perl-match.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from genesispy import reporting
from genesispy.cli import parse_args
from genesispy.reporting import GenesisPyError
from genesispy.manager import Manager


@pytest.fixture(autouse=True)
def _reset_log_state():
    """Avoid cross-test contamination of the process-global log state."""
    reporting.set_log_file(None)
    yield
    reporting.set_log_file(None)


# ----------------------------------------------------------- J1 --log default


def test_log_defaults_to_genesispy_log() -> None:
    ns = parse_args([])
    assert ns.log == "genesispy.log"


def test_log_is_lazy_opened_no_error(tmp_path: Path, monkeypatch) -> None:
    """Setting a log path does not create the file until the first
    error/warning. Clean runs leave no log artifact."""
    monkeypatch.chdir(tmp_path)
    log_path = str(tmp_path / "test.log")
    reporting.set_log_file(log_path)
    assert not os.path.exists(log_path)


def test_log_file_created_on_first_warning(tmp_path: Path) -> None:
    log_path = str(tmp_path / "test.log")
    reporting.set_log_file(log_path)
    assert not os.path.exists(log_path)
    reporting.warning("first warning")
    assert os.path.exists(log_path)
    with open(log_path) as f:
        content = f.read()
    assert "first warning" in content


def test_log_set_to_none_disables() -> None:
    reporting.set_log_file(None)
    # No file path stored; _log is a no-op.
    reporting.warning("no log path set")
    # No exception; just confirms the disable path works.


# ----------------------------------------------- J2 --product / --vf-out


def test_product_and_vf_out_mutual_exclusion(tmp_path: Path) -> None:
    """Passing both --product and --vf-out raises."""
    args = parse_args(
        ["--top", "t", "--product", "foo.vf", "--vf-out", "bar"]
    )
    with pytest.raises(GenesisPyError, match="mutually exclusive"):
        Manager(args)


def test_vf_out_auto_appends_vf(tmp_path: Path) -> None:
    """--vf-out FILE auto-appends .vf and selects single-file mode."""
    args = parse_args(["--top", "t", "--vf-out", str(tmp_path / "manifest")])
    mgr = Manager(args)
    assert mgr.product_file == str(tmp_path / "manifest") + ".vf"
    assert mgr.product_single is True


def test_vf_out_keeps_existing_vf(tmp_path: Path) -> None:
    """--vf-out FILE.vf is not double-appended."""
    args = parse_args(["--top", "t", "--vf-out", str(tmp_path / "manifest.vf")])
    mgr = Manager(args)
    assert mgr.product_file == str(tmp_path / "manifest.vf")
    assert mgr.product_single is True


def test_product_uses_triple_file_mode(tmp_path: Path) -> None:
    """--product FILE selects triple-file (master + .synth + .verif) mode."""
    args = parse_args(["--top", "t", "--product", str(tmp_path / "manifest.vf")])
    mgr = Manager(args)
    assert mgr.product_file == str(tmp_path / "manifest.vf")
    assert mgr.product_single is False


def test_no_product_flag_leaves_product_file_none(tmp_path: Path) -> None:
    args = parse_args(["--top", "t"])
    mgr = Manager(args)
    assert mgr.product_file is None
    assert mgr.product_single is False
