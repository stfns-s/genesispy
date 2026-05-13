"""Cluster H: error / warning bare-name + method form on UniqueModule.

Mirrors Perl `$self->error(msg)` / bare `error(msg)` in .vpy bodies
(UniqueModule.pm:2803-2860). Both forms prefix the message with the
current module and instance path so the failure points at the
elaboration source.
"""

from __future__ import annotations

from pathlib import Path
import importlib.util

import pytest

from genesispy import cache
from genesispy.reporting import GenesisPyError
from genesispy.template import emitter
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


# ------------------------------------------------------ self.error / self.warning


def test_self_error_raises_with_module_prefix(capsys) -> None:
    """self.error(msg) raises GenesisPyError; stderr carries module prefix."""
    class _Mod(UniqueModule):
        pass

    inst = _Mod(StubManager())
    with pytest.raises(GenesisPyError) as excinfo:
        inst.error("user-facing message")
    msg = str(excinfo.value)
    assert "_Mod" in msg
    assert "user-facing message" in msg
    # stderr should also carry the prefixed message.
    err = capsys.readouterr().err
    assert "_Mod" in err
    assert "user-facing message" in err


def test_self_warning_does_not_raise(capsys) -> None:
    """self.warning(msg) prints to stderr but returns normally."""
    class _Mod(UniqueModule):
        pass

    inst = _Mod(StubManager())
    inst.warning("non-fatal note")
    err = capsys.readouterr().err
    assert "_Mod" in err
    assert "non-fatal note" in err


# ----------------------------------------------------- bare-name in .vpy body


def _emit_and_load(tmp_path: Path, name: str, vpy_text: str):
    vpy = tmp_path / f"{name}.vpy"
    vpy.write_text(vpy_text)
    out_dir = tmp_path / "raw"
    py_path = emitter.write_module(str(vpy), str(out_dir))
    spec = importlib.util.spec_from_file_location(f"_gen_{name}", py_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, name)


def test_bare_error_in_vpy_body_raises(tmp_path: Path, capsys) -> None:
    """A `.vpy` body using bare `error("msg")` raises with module prefix.

    Pre-Cluster-H this would have raised NameError -- the bare name was
    never bound. After H, it routes to self.error.
    """
    text = (
        "module bad_mod;\n"
        "//; error('boom')\n"
        "endmodule\n"
    )
    cls = _emit_and_load(tmp_path, "bad_mod", text)
    inst = cls(StubManager())
    with pytest.raises(GenesisPyError) as excinfo:
        inst.execute()
    assert "bad_mod" in str(excinfo.value)
    assert "boom" in str(excinfo.value)


def test_bare_warning_in_vpy_body(tmp_path: Path, capsys) -> None:
    """A `.vpy` body using bare `warning("msg")` prints and continues."""
    text = (
        "module warn_mod;\n"
        "//; warning('non-fatal')\n"
        "//; emit('// after warning')\n"
        "endmodule\n"
    )
    cls = _emit_and_load(tmp_path, "warn_mod", text)
    inst = cls(StubManager())
    inst.execute()
    err = capsys.readouterr().err
    assert "warn_mod" in err
    assert "non-fatal" in err
    # Elaboration continued past the warning.
    out = cache.OUTFILE_CONTENT_CACHE[f"{inst.get_unique_module_name()}.v"]
    assert "// after warning" in out


# ------------------------------------------------------------ alias_dict path


def test_alias_dict_exposes_error_and_warning() -> None:
    """alias_dict() must include error and warning bindings for include()-d
    .vpy bodies (which exec in a fresh namespace not seeing the generated
    module's module-level imports)."""
    from genesispy.template.aliases import alias_dict

    class _Mod(UniqueModule):
        pass

    inst = _Mod(StubManager())
    d = alias_dict(inst)
    assert "error" in d
    assert "warning" in d
    # The bindings should be the self.error / self.warning methods.
    assert callable(d["error"])
    assert callable(d["warning"])
