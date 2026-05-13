"""Cluster B: sub-instance accessors (get_subinst / exists_subinst /
get_subinst_array / get_instance_obj / search_subinst).

Mirrors Perl UniqueModule.pm:760, :780, :932, :1087, :797.
"""

from __future__ import annotations

import pytest

from genesispy import cache
from genesispy.reporting import ElaborationError
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


class _Top(UniqueModule):
    pass


class _Mid(UniqueModule):
    def execute(self) -> None:
        self.parameter("WIDTH", 8)
        super().execute()


class _Leaf(UniqueModule):
    def execute(self) -> None:
        self.parameter("LANES", 4)
        super().execute()


# ---------------------------------------------------------------- get_subinst


def test_get_subinst_returns_named_instance() -> None:
    top = _Top(StubManager())
    leaf = top.unique_inst(_Leaf, "u_leaf")
    assert top.get_subinst("u_leaf") is leaf


def test_get_subinst_raises_when_missing() -> None:
    top = _Top(StubManager())
    with pytest.raises(ElaborationError, match="get_subinst"):
        top.get_subinst("u_nope")


# --------------------------------------------------------------- exists_subinst


def test_exists_subinst_returns_bool() -> None:
    top = _Top(StubManager())
    top.unique_inst(_Leaf, "u_leaf")
    assert top.exists_subinst("u_leaf") is True
    assert top.exists_subinst("u_nope") is False


# ------------------------------------------------------------ get_subinst_array


def test_get_subinst_array_empty_pattern_returns_all() -> None:
    top = _Top(StubManager())
    a = top.unique_inst(_Leaf, "u_a")
    b = top.unique_inst(_Leaf, "u_b")
    arr = top.get_subinst_array()
    assert set(arr) == {a, b}


def test_get_subinst_array_regex_filter() -> None:
    top = _Top(StubManager())
    a = top.unique_inst(_Leaf, "u_a")
    top.unique_inst(_Leaf, "x_b")
    arr = top.get_subinst_array(r"^u_")
    assert arr == [a]


# ------------------------------------------------------------ get_instance_obj


def test_get_instance_obj_passthrough_for_module() -> None:
    top = _Top(StubManager())
    leaf = top.unique_inst(_Leaf, "u_leaf")
    assert top.get_instance_obj(leaf) is leaf


def test_get_instance_obj_walks_dotted_path() -> None:
    mgr = StubManager()
    top = _Top(mgr)
    top._instance_name = "core"
    mid = top.unique_inst(_Mid, "u_mid")
    leaf = mid.unique_inst(_Leaf, "u_leaf")
    assert top.get_instance_obj("core") is top
    assert top.get_instance_obj("core.u_mid") is mid
    assert top.get_instance_obj("core.u_mid.u_leaf") is leaf


def test_get_instance_obj_raises_on_bad_root() -> None:
    top = _Top(StubManager())
    top._instance_name = "core"
    with pytest.raises(ElaborationError, match="legal instance path"):
        top.get_instance_obj("wrong_root.u_mid")


def test_get_instance_obj_raises_on_missing_subinst() -> None:
    top = _Top(StubManager())
    top._instance_name = "core"
    top.unique_inst(_Mid, "u_mid")
    with pytest.raises(ElaborationError, match="cannot find subinst"):
        top.get_instance_obj("core.u_mid.u_nope")


# ------------------------------------------------------------- search_subinst


def test_search_subinst_default_walks_full_tree() -> None:
    top = _Top(StubManager())
    top._instance_name = "top"
    mid = top.unique_inst(_Mid, "u_mid")
    leaf = mid.unique_inst(_Leaf, "u_leaf")
    found = top.search_subinst()
    # DFS pre-order: top, mid, leaf.
    assert found == [top, mid, leaf]


def test_search_subinst_reverse_post_order() -> None:
    top = _Top(StubManager())
    top._instance_name = "top"
    mid = top.unique_inst(_Mid, "u_mid")
    leaf = mid.unique_inst(_Leaf, "u_leaf")
    found = top.search_subinst(reverse=True)
    # Reverse: leaf, mid, top.
    assert found == [leaf, mid, top]


def test_search_subinst_depth_zero_returns_only_start() -> None:
    top = _Top(StubManager())
    top._instance_name = "top"
    top.unique_inst(_Mid, "u_mid")
    assert top.search_subinst(depth=0) == [top]


def test_search_subinst_start_from_object() -> None:
    top = _Top(StubManager())
    top._instance_name = "top"
    mid = top.unique_inst(_Mid, "u_mid")
    leaf = mid.unique_inst(_Leaf, "u_leaf")
    found = top.search_subinst(start_from=mid)
    assert found == [mid, leaf]


def test_search_subinst_start_from_string_path() -> None:
    top = _Top(StubManager())
    top._instance_name = "top"
    mid = top.unique_inst(_Mid, "u_mid")
    leaf = mid.unique_inst(_Leaf, "u_leaf")
    found = top.search_subinst(start_from="top.u_mid")
    assert found == [mid, leaf]


def test_search_subinst_iname_regex() -> None:
    top = _Top(StubManager())
    top._instance_name = "top"
    a = top.unique_inst(_Leaf, "u_a")
    top.unique_inst(_Leaf, "x_b")
    found = top.search_subinst(iname_regex=r"^u_")
    assert found == [a]


def test_search_subinst_bname_regex() -> None:
    top = _Top(StubManager())
    top._instance_name = "top"
    mid = top.unique_inst(_Mid, "u_mid")
    leaf = mid.unique_inst(_Leaf, "u_leaf")
    found = top.search_subinst(bname_regex=r"_Leaf$")
    assert found == [leaf]


def test_search_subinst_has_param_regex_string() -> None:
    """has_param_regex='WIDTH' returns nodes whose param list includes WIDTH."""
    top = _Top(StubManager())
    top._instance_name = "top"
    mid = top.unique_inst(_Mid, "u_mid")  # defines WIDTH
    leaf = mid.unique_inst(_Leaf, "u_leaf")  # defines LANES (not WIDTH)
    found = top.search_subinst(has_param_regex="WIDTH")
    assert found == [mid]


def test_search_subinst_apply_map_callable() -> None:
    top = _Top(StubManager())
    top._instance_name = "top"
    a = top.unique_inst(_Leaf, "u_a")
    top.unique_inst(_Mid, "u_mid")  # different class
    found = top.search_subinst(apply_map=lambda n: isinstance(n, _Leaf))
    assert found == [a]


def test_search_subinst_compose_filters_and() -> None:
    """Multiple filters AND together."""
    top = _Top(StubManager())
    top._instance_name = "top"
    mid = top.unique_inst(_Mid, "u_mid")
    mid.unique_inst(_Leaf, "u_leaf")
    top.unique_inst(_Leaf, "x_other")
    found = top.search_subinst(iname_regex=r"^u_", bname_regex=r"_Leaf$")
    # Only u_leaf matches both (u_mid fails bname; x_other fails iname).
    assert len(found) == 1
    assert str(found[0].iname) == "u_leaf"
