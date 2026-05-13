"""Cluster D: exists_param / get_top_param / list_params.

Mirrors Perl UniqueModule.pm:496 / :550 / :515.
"""

from __future__ import annotations

import pytest

from genesispy import cache
from genesispy.reporting import ParameterError
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


class _Top(UniqueModule):
    pass


class _Leaf(UniqueModule):
    def execute(self) -> None:
        self.parameter("WIDTH", 8)
        self.parameter("LANES", 4)
        super().execute()


def test_exists_param_returns_bool() -> None:
    inst = _Top(StubManager())
    inst.parameter("WIDTH", 8)
    assert inst.exists_param("WIDTH") is True
    assert inst.exists_param("UNKNOWN") is False


def test_list_params_returns_sorted_names() -> None:
    inst = _Leaf(StubManager())
    inst.execute()
    names = inst.list_params()
    assert names == sorted(names)
    assert set(names) == {"WIDTH", "LANES"}


def test_list_params_distinct_from_get_mod_param_list() -> None:
    """list_params() returns a list of names, get_mod_param_list() returns
    a dict of {name: value}. Both should be available."""
    inst = _Leaf(StubManager())
    inst.execute()
    assert isinstance(inst.list_params(), list)
    assert isinstance(inst.get_mod_param_list(), dict)
    assert set(inst.list_params()) == set(inst.get_mod_param_list().keys())


def test_get_top_param_returns_top_value() -> None:
    top = _Top(StubManager())
    top.parameter("CLK_HZ", 100_000_000)
    leaf = top.unique_inst(_Leaf, "u_leaf")
    assert leaf.get_top_param("CLK_HZ") == 100_000_000


def test_get_top_param_raises_on_unknown() -> None:
    top = _Top(StubManager())
    leaf = top.unique_inst(_Leaf, "u_leaf")
    with pytest.raises(ParameterError):
        leaf.get_top_param("NEVER_DEFINED")
