"""Tests for genesispy.user_config — the user-facing config facade."""

from __future__ import annotations

import os

import pytest

from genesispy import user_config
from genesispy.config_handler import ConfigHandler
from genesispy.unique_module import UniqueModule
from genesispy import cache

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()
    user_config._active_manager = None
    user_config._active_module = None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
class _Top(UniqueModule):
    pass


class _RealishManager:
    """Minimal manager carrying a real ConfigHandler + the attrs we need."""

    def __init__(
        self, top: str = "Top", synth_dir: str = "genesis_synth"
    ) -> None:
        # ConfigHandler reads ``args.parameter`` and ``args.unq_style``.
        class _Args:
            parameter: list = []
            unq_style = None

        self.args = _Args()
        self.top = top
        self.debug = 0
        self.src_path: list = []
        self.inc_path: list = []
        self.output_dir = synth_dir
        self.raw_dir = synth_dir
        self.synth_dir = synth_dir
        self.verif_dir = synth_dir
        self.cfg_handler = ConfigHandler(self)

    def find_file(self, name: str, paths=None):
        if os.path.isabs(name):
            if os.path.exists(name):
                return name
            raise FileNotFoundError(name)
        search = paths if paths is not None else (self.src_path + self.inc_path)
        for d in search:
            cand = os.path.join(d, name)
            if os.path.exists(cand):
                return os.path.abspath(cand)
        raise FileNotFoundError(
            f"find_file: file '{name}' not found in {list(search)}"
        )


# --------------------------------------------------------------------------
# Context absence
# --------------------------------------------------------------------------
def test_configure_without_context_raises_clear_error() -> None:
    with pytest.raises(RuntimeError, match="no active manager context"):
        user_config._configure("X", 42)


def test_get_configuration_without_context_raises() -> None:
    with pytest.raises(RuntimeError, match="no active manager context"):
        user_config._get_configuration("X")


def test_include_without_context_raises(tmp_path) -> None:
    # parse will succeed for an empty file but exec needs current module.
    p = tmp_path / "empty.vpy"
    p.write_text("")
    with pytest.raises(RuntimeError, match="no active module context"):
        user_config._include(str(p))


# --------------------------------------------------------------------------
# Context manager
# --------------------------------------------------------------------------
def test_context_manager_sets_and_clears() -> None:
    mgr = _RealishManager()
    top = _Top(mgr)
    assert user_config._active_manager is None
    assert user_config._active_module is None
    with user_config.context(mgr, top):
        assert user_config._current_manager() is mgr
        assert user_config._current_module() is top
    assert user_config._active_manager is None
    assert user_config._active_module is None


def test_context_manager_clears_on_exception() -> None:
    mgr = _RealishManager()
    top = _Top(mgr)
    with pytest.raises(ValueError):
        with user_config.context(mgr, top):
            raise ValueError("boom")
    assert user_config._active_manager is None
    assert user_config._active_module is None


# --------------------------------------------------------------------------
# configure / get_configuration round-trip
# --------------------------------------------------------------------------
def test_configure_get_round_trip() -> None:
    mgr = _RealishManager()
    top = _Top(mgr)
    with user_config.context(mgr, top):
        user_config._configure("WIDTH", 32)
        assert user_config._get_configuration("WIDTH") == 32


def test_get_configuration_honours_scoped_cli_override() -> None:
    """`_get_configuration` honours the active module's instance path."""
    import argparse
    mgr = _RealishManager()
    # Re-init ConfigHandler with a scoped --parameter on the top.
    mgr.args = argparse.Namespace(parameter=["Top.WIDTH=64"], unq_style=None)
    mgr.cfg_handler = ConfigHandler(mgr)
    top = _Top(mgr)
    top._instance_name = "Top"  # path segments derive from instance name
    with user_config.context(mgr, top):
        assert user_config._get_configuration("WIDTH") == 64


def test_exists_and_remove_configuration() -> None:
    mgr = _RealishManager()
    top = _Top(mgr)
    with user_config.context(mgr, top):
        user_config._configure("X", "hello")
        assert user_config._exists_configuration("X") is True
        user_config._remove_configuration("X")
        assert user_config._exists_configuration("X") is False


def test_print_configuration_returns_string() -> None:
    mgr = _RealishManager()
    top = _Top(mgr)
    with user_config.context(mgr, top):
        user_config._configure("Y", 1)
        out = user_config._print_configuration()
    assert isinstance(out, str)
    assert "Y" in out
    assert "1" in out


# --------------------------------------------------------------------------
# include()
# --------------------------------------------------------------------------
def test_include_runs_vpy_in_current_module(tmp_path) -> None:
    mgr = _RealishManager()
    top = _Top(mgr)
    p = tmp_path / "frag.vpy"
    # ``//;`` lines are Python; this template just calls configure().
    p.write_text(
        "//; from genesispy.user_config import _configure as configure\n"
        "//; configure('X', 42)\n"
    )
    with user_config.context(mgr, top):
        user_config._include(str(p))
        assert user_config._get_configuration("X") == 42


def test_include_injects_perl_compat_aliases(tmp_path) -> None:
    """Bare ``parameter`` / ``emit`` callable from inside an included .vpy."""
    mgr = _RealishManager()
    top = _Top(mgr)
    p = tmp_path / "frag.vpy"
    p.write_text(
        "//; w = parameter('WIDTH', 8)\n"
        "//; emit(f'// frag-WIDTH={w}')\n"
    )
    with user_config.context(mgr, top):
        user_config._include(str(p))
    assert top._outfile_handle is not None
    assert "// frag-WIDTH=8" in top._outfile_handle.getvalue()


def test_include_resolves_relative_via_includepath(tmp_path) -> None:
    """``include('frag.vpy')`` should walk ``--includepath`` (Genesis2 parity)."""
    inc_dir = tmp_path / "inc"
    inc_dir.mkdir()
    (inc_dir / "frag.vpy").write_text(
        "//; from genesispy.user_config import _configure as configure\n"
        "//; configure('X', 99)\n"
    )
    mgr = _RealishManager()
    mgr.inc_path = [str(inc_dir)]
    top = _Top(mgr)
    with user_config.context(mgr, top):
        user_config._include("frag.vpy")
        assert user_config._get_configuration("X") == 99


def test_include_relative_not_on_includepath_raises(tmp_path) -> None:
    mgr = _RealishManager()
    mgr.inc_path = [str(tmp_path / "nowhere")]
    top = _Top(mgr)
    with user_config.context(mgr, top):
        with pytest.raises(FileNotFoundError):
            user_config._include("missing.vpy")


def test_include_registers_line_map(tmp_path) -> None:
    """Tracebacks from an included .vpy report .vpy line numbers."""
    from genesispy.template import runtime

    mgr = _RealishManager()
    top = _Top(mgr)
    p = tmp_path / "boom.vpy"
    p.write_text(
        "module boom;\n"
        "//; raise ValueError('detonated')\n"
        "endmodule\n"
    )
    runtime.clear_line_maps()
    with user_config.context(mgr, top):
        with pytest.raises(ValueError, match="detonated"):
            user_config._include(str(p))
    assert str(p) in runtime.LINE_MAP
    # The raise is on .vpy line 2 → must be present in the registered map.
    assert any(
        src_lineno == 2 for _, src_lineno in runtime.LINE_MAP[str(p)].values()
    )


def test_include_self_is_current_module(tmp_path) -> None:
    """Plain Verilog lines in the included file should call ``self.emit``."""
    mgr = _RealishManager()
    top = _Top(mgr)
    p = tmp_path / "frag.vpy"
    p.write_text("hello world\n")
    with user_config.context(mgr, top):
        user_config._include(str(p))
    assert top._outfile_handle is not None
    assert "hello world" in top._outfile_handle.getvalue()


# --------------------------------------------------------------------------
# get_top_name / get_synthtop_path
# --------------------------------------------------------------------------
def test_get_top_name_returns_manager_top() -> None:
    mgr = _RealishManager(top="my_top")
    top = _Top(mgr)
    with user_config.context(mgr, top):
        assert user_config._get_top_name() == "my_top"


def test_get_synthtop_path_is_absolute() -> None:
    mgr = _RealishManager(synth_dir="genesis_synth")
    top = _Top(mgr)
    with user_config.context(mgr, top):
        path = user_config._get_synthtop_path()
    assert os.path.isabs(path)
    assert path.endswith("genesis_synth")


def test_error_helper_raises() -> None:
    mgr = _RealishManager()
    top = _Top(mgr)
    with user_config.context(mgr, top):
        with pytest.raises(Exception):
            user_config.error("boom")


# Review 11 #173 -- context() must save/restore prior values, not clear to None.
def test_context_nests_correctly() -> None:
    """A nested `with context(...)` must restore the outer values on exit."""
    mgr1 = _RealishManager()
    mgr2 = _RealishManager()
    top1 = _Top(mgr1)
    top2 = _Top(mgr2)
    with user_config.context(mgr1, top1):
        assert user_config._active_manager is mgr1
        assert user_config._active_module is top1
        with user_config.context(mgr2, top2):
            assert user_config._active_manager is mgr2
            assert user_config._active_module is top2
        assert user_config._active_manager is mgr1
        assert user_config._active_module is top1
    assert user_config._active_manager is None
    assert user_config._active_module is None
