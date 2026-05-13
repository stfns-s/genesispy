"""Cluster I: .cfg sandbox now injects get_top_name, get_synthtop_path,
print_configuration to match Perl (ConfigHandler.pm:244-258).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from genesispy.cli import parse_args
from genesispy.manager import Manager


def _write_cfg(tmp_path: Path, body: str) -> str:
    cfg = tmp_path / "u.cfg"
    cfg.write_text(body)
    return str(cfg)


def _run_manager_with_cfg(cfg_path: str, top: str = "demo_top") -> Manager:
    args = parse_args(
        [
            "--top", top,
            "--cfg", cfg_path,
            "--out-dir", "/tmp/_cfg_test_out",
            "--raw-dir", "/tmp/_cfg_test_raw",
        ]
    )
    return Manager(args)


def test_cfg_get_top_name_resolves(tmp_path: Path) -> None:
    """A .cfg script can call get_top_name() and receive Manager.top."""
    cfg = _write_cfg(
        tmp_path,
        "name = get_top_name()\n"
        "if name != 'demo_top':\n"
        "    raise AssertionError(f'expected demo_top, got {name!r}')\n",
    )
    mgr = _run_manager_with_cfg(cfg)
    # Lazily resolve cfg_handler so .cfg is read.
    mgr._ensure_cfg_handler()
    # No exception -> the script's assertion passed.


def test_cfg_get_synthtop_path_resolves(tmp_path: Path) -> None:
    """A .cfg script can call get_synthtop_path() and receive synth_dir."""
    cfg = _write_cfg(
        tmp_path,
        "path = get_synthtop_path()\n"
        "if not isinstance(path, str) or not path:\n"
        "    raise AssertionError(f'bad path: {path!r}')\n",
    )
    mgr = _run_manager_with_cfg(cfg)
    mgr._ensure_cfg_handler()


def test_cfg_print_configuration_callable(tmp_path: Path, capsys) -> None:
    """A .cfg script can call print_configuration() without NameError."""
    cfg = _write_cfg(
        tmp_path,
        "configure('A', 1)\n"
        "print_configuration()\n",
    )
    mgr = _run_manager_with_cfg(cfg)
    mgr._ensure_cfg_handler()
    # The method exists and was callable.
