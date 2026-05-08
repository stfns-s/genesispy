"""Tests for genesispy.hashing."""

from __future__ import annotations

from genesispy.hashing import _canonical, sha256_param_signature


def test_deterministic() -> None:
    a = sha256_param_signature("Foo", {"WIDTH": 8, "DEPTH": 16})
    b = sha256_param_signature("Foo", {"WIDTH": 8, "DEPTH": 16})
    assert a == b
    assert len(a) == 64


def test_param_order_irrelevant() -> None:
    a = sha256_param_signature("Foo", {"WIDTH": 8, "DEPTH": 16})
    b = sha256_param_signature("Foo", {"DEPTH": 16, "WIDTH": 8})
    assert a == b


def test_module_name_matters() -> None:
    a = sha256_param_signature("Foo", {"WIDTH": 8})
    b = sha256_param_signature("Bar", {"WIDTH": 8})
    assert a != b


def test_value_change_changes_hash() -> None:
    a = sha256_param_signature("Foo", {"WIDTH": 8})
    b = sha256_param_signature("Foo", {"WIDTH": 9})
    assert a != b


def test_nested_dict_canonicalised() -> None:
    a = sha256_param_signature("Foo", {"OPTS": {"a": 1, "b": 2}})
    b = sha256_param_signature("Foo", {"OPTS": {"b": 2, "a": 1}})
    assert a == b


def test_list_vs_tuple_equivalent() -> None:
    a = sha256_param_signature("Foo", {"P": [1, 2, 3]})
    b = sha256_param_signature("Foo", {"P": (1, 2, 3)})
    assert a == b


def test_canonical_passthrough_types() -> None:
    assert _canonical(1) == 1
    assert _canonical(1.5) == 1.5
    assert _canonical("x") == "x"
    assert _canonical(True) is True
    assert _canonical(None) is None


def test_canonical_unknown_uses_repr() -> None:
    class Weird:
        def __repr__(self) -> str:
            return "<weird>"

    assert _canonical(Weird()) == "<weird>"


def test_canonical_dict_str_collision_raises() -> None:
    import pytest

    # int 1 and str "1" both stringify to "1" -> must raise, not silently
    # drop one value.
    with pytest.raises(TypeError, match="collapse under str"):
        _canonical({1: "a", "1": "b"})
