"""Runtime check that bare-name aliases work inside generated execute()."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from genesispy import cache
from genesispy.template import emitter

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


def _emit_and_load(tmp_path: Path, name: str, vpy_text: str):
    """Helper: write a .vpy, emit + load, return the generated class."""
    vpy = tmp_path / f"{name}.vpy"
    vpy.write_text(vpy_text)
    out_dir = tmp_path / "raw"
    py_path = emitter.write_module(str(vpy), str(out_dir))
    spec = importlib.util.spec_from_file_location(f"_gen_{name}", py_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, name)


def test_bare_parameter_call_works(tmp_path: Path) -> None:
    """A .vpy using bare ``parameter(...)`` elaborates without error."""
    text = (
        "module foo;\n"
        "//; w = parameter('WIDTH', 8)\n"
        "//; emit(f'// WIDTH={w}')\n"
        "endmodule\n"
    )
    cls = _emit_and_load(tmp_path, "foo", text)
    inst = cls(StubManager())
    inst.execute()
    out = cache.OUTFILE_CONTENT_CACHE[f"{inst.get_unique_module_name()}.v"]
    assert "// WIDTH=8" in out


def test_alias_rebinding_user_local_wins(tmp_path: Path) -> None:
    """User can shadow ``parameter`` with their own local; the rebinding wins.

    Standard Python scoping: aliases are just locals, so ``parameter = "x"``
    in the user's body simply rebinds the name. We assert that:
      - the rebinding sticks within the same execute()
      - the original alias still works in a *fresh* module instance
    """
    text = (
        "module foo;\n"
        "//; parameter = 'shadowed'\n"
        "//; emit(f'// got={parameter}')\n"
        "endmodule\n"
    )
    cls = _emit_and_load(tmp_path, "foo_shadow", text)
    inst = cls(StubManager())
    inst.execute()
    key = f"{inst.get_unique_module_name()}.v"
    assert "// got=shadowed" in cache.OUTFILE_CONTENT_CACHE[key]

    # Fresh instance: alias is rebound at the top of execute() again, so
    # the original ``parameter`` callable is restored.
    text2 = (
        "module foo;\n"
        "//; w = parameter('WIDTH', 32)\n"
        "//; emit(f'// w={w}')\n"
        "endmodule\n"
    )
    cls2 = _emit_and_load(tmp_path, "foo_fresh", text2)
    inst2 = cls2(StubManager())
    inst2.execute()
    out2 = cache.OUTFILE_CONTENT_CACHE[f"{inst2.get_unique_module_name()}.v"]
    assert "// w=32" in out2


def test_bare_emit_call_works(tmp_path: Path) -> None:
    text = (
        "module foo;\n"
        "//; emit('// bare-emit-ok')\n"
        "endmodule\n"
    )
    cls = _emit_and_load(tmp_path, "foo_emit", text)
    inst = cls(StubManager())
    inst.execute()
    out = cache.OUTFILE_CONTENT_CACHE[f"{inst.get_unique_module_name()}.v"]
    assert "// bare-emit-ok" in out


# Review 11 #150 -- alias_dict must include the StrCallable shortname quartet
# so that include()-d .vpy code can use `mname` / `iname` / `bname` / `sname`.
def test_alias_dict_binds_strcallable_shortnames() -> None:
    """`alias_dict(mod)` must expose mname/iname/bname/sname.

    The emitter prelude (`template/emitter._header`) and the gvpy class
    factory both bind these four `StrCallable` aliases at the top of
    `execute()`. CLAUDE.md promises the same surface from
    `user_config._include`, which builds its exec-globals dict via
    `alias_dict`. Today `alias_dict` omits the quartet, so an `include()`-d
    .vpy referencing `` `mname` `` raises `NameError`.
    """
    from genesispy.template.aliases import alias_dict
    from genesispy.template.runtime import StrCallable

    inst = StubManager()  # any object with the four attrs would do
    # Mimic a UniqueModule with the four shortnames already populated.
    class _ModStub:
        # SIMPLE_ALIASES targets (must exist as attrs even if no-op).
        parameter = define_param = doc_param = param_range = None
        exists_param = get_top_param = list_params = None
        synonym = instantiate = emit = None
        error = warning = None
        get_subinst = exists_subinst = get_subinst_array = None
        get_instance_obj = search_subinst = None
        unique_inst = unique_inst_param = clone_inst = ununique_inst = None
        generate = generate_w_name = None
        pinclude = None
        # The four StrCallable shortnames the emitter binds at execute() top.
        mname = StrCallable("Foo_unq0")
        iname = StrCallable("u_foo")
        bname = StrCallable("Foo")
        sname = StrCallable("Foo_unq0")

    d = alias_dict(_ModStub())
    for key in ("mname", "iname", "bname", "sname"):
        assert key in d, f"alias_dict() missing {key!r} -- include()-d .vpy will NameError"
    assert str(d["mname"]) == "Foo_unq0"
    assert str(d["iname"]) == "u_foo"
