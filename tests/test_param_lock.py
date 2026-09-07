"""Parameters lock after the body has run, as in Genesis2 (UniqueModule.pm:833,
1246, 314-326, 2443-2452, 2296, 2183-2189)."""

from __future__ import annotations

import pytest

from ._stubs import StubManager
from genesispy.reporting import ParameterError
from genesispy.unique_module import UniqueModule


class _Top(UniqueModule):
    def execute(self):
        super().execute()


class _Leaf(UniqueModule):
    def execute(self):
        super().execute()
        self.parameter("W", 4)


class _MeddlingLeaf(UniqueModule):
    """A body that writes to its parent's parameters."""
    def execute(self):
        super().execute()
        self._parent.override_param("X", 1)


class _Forcer(UniqueModule):
    def execute(self):
        super().execute()
        self.parameter("W", 4)
        self.parameter("W", 8, force=True)   # legal: a different level
        self.parameter("PUB", 3, force=True)


def test_writes_are_fatal_after_elaboration() -> None:
    top = _Top(StubManager())
    leaf = top.unique_inst(_Leaf, "u0")
    for call in (
        lambda: leaf.override_param("W", 9),
        lambda: leaf.force_param("W", 9),
        lambda: leaf.define_param("Z", 1),
        lambda: leaf.parameter("Z", 1),
    ):
        with pytest.raises(ParameterError, match="not allowed at this point"):
            call()
    assert leaf.get_param("W") == 4


def test_parent_is_frozen_while_a_child_elaborates() -> None:
    top = _Top(StubManager())
    top.parameter("X", 0)
    with pytest.raises(ParameterError, match="not allowed at this point"):
        top.unique_inst(_MeddlingLeaf, "u0")
    top.override_param("X", 2)   # the parent reopens after the child returns
    assert top.get_param("X") == 2


def test_clone_takes_no_parameters() -> None:
    top = _Top(StubManager())
    leaf = top.unique_inst(_Leaf, "u0")
    clone = top.clone_inst(leaf, "u1")
    with pytest.raises(ParameterError, match="not allowed at this point"):
        clone.override_param("W", 9)
    assert clone.get_param("W") == 4


def test_second_declaration_is_fatal() -> None:
    top = _Top(StubManager())
    top.parameter("W", 4)
    with pytest.raises(ParameterError, match="already declared/seen at the same priority"):
        top.parameter("W", 8)


def test_declaration_after_a_parent_keyword_is_the_first_declaration() -> None:
    top = _Top(StubManager())
    top.override_param("W", 16)    # the keyword pass creates an undeclared entry
    assert not top.exists_param("W")
    assert top.parameter("W", 4) == 16
    assert top.exists_param("W")
    with pytest.raises(ParameterError, match="already declared/seen"):
        top.parameter("W", 4)


def test_force_after_declaration_is_legal_and_a_second_force_is_fatal() -> None:
    top = _Top(StubManager())
    leaf = top.unique_inst(_Forcer, "u0")
    assert leaf.get_param("W") == 8
    assert leaf.get_param("PUB") == 3
    fresh = _Top(StubManager())
    fresh.force_param("W", 1)
    with pytest.raises(ParameterError, match="already declared/seen at the same priority"):
        fresh.force_param("W", 2)


def test_get_param_of_an_undeclared_keyword_is_fatal_and_warned(capsys) -> None:
    top = _Top(StubManager())
    leaf = top.unique_inst(_Leaf, "u0", NOSUCH=1)
    with pytest.raises(ParameterError, match="never explicitly declared"):
        leaf.get_param("NOSUCH")
    assert leaf.get_mod_param_list()["NOSUCH"] == 1
    assert (
        "Parameter 'NOSUCH' was passed to _Top.u0 but it was never actually "
        "declared/used in u0" in capsys.readouterr().err
    )
