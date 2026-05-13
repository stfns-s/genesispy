"""Cluster F: iname/mname/bname/sname work as both attribute AND method-call
on instances. Mirrors Perl `$obj->mname()` / `$obj->iname()` / etc.
(UniqueModule.pm:1815-1843)."""

from __future__ import annotations

from genesispy import cache
from genesispy.template.runtime import StrCallable
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


class _Mod(UniqueModule):
    pass


class _SynonymDerived(UniqueModule):
    _synonym_for = "OriginalBase"


def test_mname_attribute_and_call_form_match() -> None:
    inst = _Mod(StubManager())
    inst._instance_name = "u_a"
    # mname returns the unique module name (StrCallable).
    assert str(inst.mname) == inst._unique_module_name
    assert str(inst.mname()) == inst._unique_module_name
    # Both forms equal as strings.
    assert inst.mname == inst.mname()


def test_iname_attribute_and_call_form_match() -> None:
    inst = _Mod(StubManager())
    inst._instance_name = "u_a"
    assert str(inst.iname) == "u_a"
    assert str(inst.iname()) == "u_a"
    assert inst.iname == inst.iname()


def test_bname_attribute_and_call_form_match() -> None:
    inst = _Mod(StubManager())
    assert str(inst.bname) == "_Mod"
    assert str(inst.bname()) == "_Mod"


def test_sname_attribute_and_call_form_match_no_synonym() -> None:
    """sname == bname when no _synonym_for; both forms return same StrCallable."""
    inst = _Mod(StubManager())
    assert str(inst.sname) == "_Mod"
    assert str(inst.sname()) == "_Mod"


def test_sname_attribute_and_call_form_match_with_synonym() -> None:
    """sname returns _synonym_for when set on the class."""
    inst = _SynonymDerived(StubManager())
    assert str(inst.sname) == "OriginalBase"
    assert str(inst.sname()) == "OriginalBase"
    assert str(inst.bname) == "_SynonymDerived"


def test_shortnames_are_strcallable_subclass_of_str() -> None:
    """The returned objects must satisfy isinstance(_, str)."""
    inst = _Mod(StubManager())
    for short in (inst.mname, inst.iname, inst.bname, inst.sname):
        assert isinstance(short, str)
        assert isinstance(short, StrCallable)
