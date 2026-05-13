"""Cluster A: synonym 2-arg overload + _synonym_for stamp + sname semantics."""

from __future__ import annotations

import pytest

from genesispy import cache
from genesispy.template.aliases import alias_dict
from genesispy.template.runtime import StrCallable
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


def _make_class(name: str, *, synonym_for: str | None = None) -> type:
    """Build a UniqueModule subclass with optional ``_synonym_for`` marker."""
    attrs: dict = {}
    if synonym_for is not None:
        attrs["_synonym_for"] = synonym_for
    return type(name, (UniqueModule,), attrs)


# -------------------------------------------------------------- sname semantics


def test_sname_falls_back_to_module_name_for_plain_class() -> None:
    """Without ``_synonym_for`` stamped on the class, sname == bname."""
    cls = _make_class("Foo")
    inst = cls(StubManager())
    assert inst.bname == "Foo"
    assert inst.sname == "Foo"  # falls back to _module_name


def test_sname_reads_synonym_for_when_set() -> None:
    """A synonym-derived class reports the source template name as sname."""
    cls = _make_class("FastFoo", synonym_for="Foo")
    inst = cls(StubManager())
    assert inst.bname == "FastFoo"     # class's own name
    assert inst.sname == "Foo"         # the source template


# -------------------------------------------------------- Manager.synonym_class


def test_manager_synonym_class_stamps_synonym_for() -> None:
    """``Manager.synonym_class`` stamps ``_synonym_for`` so sname is correct."""
    from genesispy.manager import Manager

    # Construct a minimal Manager and pre-register a class so
    # synonym_class can find it without going through file resolution.
    mgr = Manager.__new__(Manager)
    mgr._loaded_classes = {"Base": _make_class("Base")}
    mgr._generated_modules = {}
    mgr.input_files = []
    mgr.inc_path = []
    mgr.extension_map = {}

    new_cls = mgr.synonym_class("Base", "Alt")
    assert new_cls.__name__ == "Alt"
    assert issubclass(new_cls, mgr._loaded_classes["Base"])
    assert getattr(new_cls, "_synonym_for", None) == "Base"


def test_gvpy_synonym_class_stamps_synonym_for(tmp_path) -> None:
    """``_GvpyManager.synonym_class`` also stamps ``_synonym_for``."""
    from genesispy.gvpy_cli import _GvpyManager
    import argparse

    src = tmp_path / "leaf.vpy"
    src.write_text("module leaf; endmodule\n")
    args = argparse.Namespace(mname=None, parameter=[])
    mgr = _GvpyManager(args, incdirs=[str(tmp_path)])

    syn = mgr.synonym_class("leaf", "alias")
    assert getattr(syn, "_synonym_for", None) == "leaf"


# -------------------------------------------------------- alias_dict dispatcher


def test_alias_dict_synonym_one_arg_calls_self_synonym() -> None:
    """The bare-name ``synonym(name)`` 1-arg form routes to self.synonym."""
    calls: list[tuple] = []

    class _Mod:
        # SIMPLE_ALIASES attrs (must exist, even if no-ops).
        parameter = define_param = doc_param = param_range = None
        exists_param = get_top_param = list_params = None
        instantiate = emit = None
        error = warning = None
        get_subinst = exists_subinst = get_subinst_array = None
        get_instance_obj = search_subinst = None
        unique_inst = unique_inst_param = clone_inst = ununique_inst = None
        generate = generate_w_name = None
        pinclude = None
        _unique_module_name = "Foo_unq0"
        _instance_name = "u_foo"
        _module_name = "Foo"
        # sname is a property in real UniqueModule; stub returns a str.
        sname = "Foo"
        _manager = None  # not used by 1-arg form

        def synonym(self, name):
            calls.append(("self.synonym", name))
            return "ok"

    d = alias_dict(_Mod())
    result = d["synonym"]("legacy_alias")
    assert result == "ok"
    assert calls == [("self.synonym", "legacy_alias")]


def test_alias_dict_synonym_two_arg_calls_manager_synonym_class() -> None:
    """The bare-name ``synonym(src, trgt)`` 2-arg form routes to Manager.synonym_class."""
    calls: list[tuple] = []

    class _StubMgr:
        def synonym_class(self, src, trgt):
            calls.append(("mgr.synonym_class", src, trgt))
            return f"<class {trgt} from {src}>"

    class _Mod:
        parameter = define_param = doc_param = param_range = None
        exists_param = get_top_param = list_params = None
        instantiate = emit = None
        error = warning = None
        get_subinst = exists_subinst = get_subinst_array = None
        get_instance_obj = search_subinst = None
        unique_inst = unique_inst_param = clone_inst = ununique_inst = None
        generate = generate_w_name = None
        pinclude = None
        _unique_module_name = "Foo_unq0"
        _instance_name = "u_foo"
        _module_name = "Foo"
        sname = "Foo"
        _manager = _StubMgr()

        def synonym(self, name):  # would only be called by 1-arg form
            calls.append(("self.synonym", name))
            return "wrong_path"

    d = alias_dict(_Mod())
    result = d["synonym"]("Base", "Alt")
    assert result == "<class Alt from Base>"
    assert calls == [("mgr.synonym_class", "Base", "Alt")]


def test_alias_dict_synonym_zero_or_three_args_raises() -> None:
    """Dispatcher rejects 0 or >=3 args with a clear TypeError."""
    class _Mod:
        parameter = define_param = doc_param = param_range = None
        exists_param = get_top_param = list_params = None
        instantiate = emit = None
        error = warning = None
        get_subinst = exists_subinst = get_subinst_array = None
        get_instance_obj = search_subinst = None
        unique_inst = unique_inst_param = clone_inst = ununique_inst = None
        generate = generate_w_name = None
        pinclude = None
        _unique_module_name = "Foo_unq0"
        _instance_name = "u_foo"
        _module_name = "Foo"
        sname = "Foo"
        _manager = None

        def synonym(self, *_):
            return None

    d = alias_dict(_Mod())
    with pytest.raises(TypeError, match="1 or 2"):
        d["synonym"]()
    with pytest.raises(TypeError, match="1 or 2"):
        d["synonym"]("a", "b", "c")


# ------------------------------------------------ alias_dict sname is synonym-aware


def test_alias_dict_sname_reflects_synonym_for() -> None:
    """For a UniqueModule whose class carries ``_synonym_for``, alias_dict's
    sname binding returns the source template name (not _unique_module_name)."""
    cls = _make_class("Alt", synonym_for="Base")
    inst = cls(StubManager())
    d = alias_dict(inst)
    assert str(d["sname"]) == "Base"
    assert str(d["bname"]) == "Alt"


# --------------------------------------------- prelude source emits synonym def


def test_alias_prelude_source_contains_synonym_dispatcher() -> None:
    """The prelude source generated for every module body defines the
    synonym dispatcher (not a plain ``synonym = self.synonym`` binding)."""
    from genesispy.template.aliases import alias_prelude_source

    src = alias_prelude_source(indent="    ")
    # The plain 1:1 binding form must NOT appear for synonym.
    assert "synonym = self.synonym" not in src
    # The dispatcher def must appear.
    assert "def synonym(*_args):" in src
    assert "self._manager.synonym_class(*_args)" in src


def test_alias_prelude_source_sname_is_synonym_aware() -> None:
    """The prelude binds sname via the synonym-aware expression."""
    from genesispy.template.aliases import alias_prelude_source

    src = alias_prelude_source(indent="    ")
    # The old (wrong) binding must be gone.
    assert "sname = StrCallable(self._unique_module_name)" not in src
    # The synonym-aware binding must be present.
    assert "_synonym_for" in src
    assert "self._module_name" in src
