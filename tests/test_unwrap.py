"""Unit tests for config_handler unwrap helpers (JSON-native shape).

Verifies that ``_unwrap_array`` / ``_unwrap_hash`` / ``_find_param``
correctly handle the JSON-native shape used by genesispy core.
"""

from __future__ import annotations

import pytest

from genesispy import config_handler as ch


# --- _unwrap_array -------------------------------------------------------- #


def test_unwrap_array_native_list():
    assert ch._unwrap_array([1, 2, 3]) == [1, 2, 3]


def test_unwrap_array_native_with_mixed_types():
    assert ch._unwrap_array([1, "two", True, None]) == [1, "two", True, None]


def test_unwrap_array_native_nested_list():
    assert ch._unwrap_array([[1, 2], [3, 4]]) == [[1, 2], [3, 4]]


def test_unwrap_array_native_with_native_dict_inside():
    assert ch._unwrap_array([{"a": 1, "b": 2}]) == [{"a": 1, "b": 2}]


# --- _unwrap_hash --------------------------------------------------------- #


def test_unwrap_hash_native_dict():
    assert ch._unwrap_hash({"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_unwrap_hash_native_with_nested_array_value():
    assert ch._unwrap_hash({"d": [1, 2, 3]}) == {"d": [1, 2, 3]}


def test_unwrap_hash_native_with_nested_dict_value():
    assert ch._unwrap_hash({"d": {"x": 1}}) == {"d": {"x": 1}}


# --- _find_param ------------------------------------------------------ #


def test_find_param_native_scalar():
    db = {
        "HierarchyTop": {
            "Parameters": [{"Name": "N", "__Val__": 8}]
        }
    }
    assert ch._find_param(db, "N") == 8


def test_find_param_native_array():
    db = {
        "HierarchyTop": {
            "Parameters": [{"Name": "WS", "__ArrayType__": [2, 5, 16]}]
        }
    }
    assert ch._find_param(db, "WS") == [2, 5, 16]


def test_find_param_native_hash():
    db = {
        "HierarchyTop": {
            "Parameters": [{"Name": "CFG", "__HashType__": {"a": 1, "b": 2}}]
        }
    }
    assert ch._find_param(db, "CFG") == {"a": 1, "b": 2}


def test_find_param_skips_user_data_inside_hash():
    """A user __HashType__ with a 'Name' key must not shadow real param lookup."""
    db = {
        "HierarchyTop": {
            "Parameters": [
                {
                    "Name": "CFG",
                    "__HashType__": {
                        "Name": "fake-param",
                        "Val": "should-not-match",
                    },
                },
                {"Name": "REAL", "__Val__": 42},
            ]
        }
    }
    assert ch._find_param(db, "fake-param") is ch._MISSING
    assert ch._find_param(db, "REAL") == 42


def test_find_param_user_hash_with_reserved_legacy_keys_preserved():
    """A user hash whose keys are literally 'ArrayType' / 'HashType' / 'Val'
    must NOT trigger wrapper interpretation. Only the double-underscored
    sentinels are reserved."""
    db = {
        "HierarchyTop": {
            "Parameters": [
                {
                    "Name": "CFG",
                    "__HashType__": {"ArrayType": "user-x", "Val": "user-y"},
                }
            ]
        }
    }
    assert ch._find_param(db, "CFG") == {
        "ArrayType": "user-x",
        "Val": "user-y",
    }


def test_find_param_returns_missing_sentinel_when_absent():
    db = {"HierarchyTop": {"Parameters": []}}
    assert ch._find_param(db, "NOPE") is ch._MISSING


def test_find_param_first_match_wins():
    db = {
        "Parameters": [
            {"Name": "X", "__Val__": 1},
            {"Name": "X", "__Val__": 2},
        ]
    }
    assert ch._find_param(db, "X") == 1


# Pin D22b-2: scalar coercion and plain-container recursion in _unwrap_array.
def test_unwrap_array_string_scalars_coerced() -> None:
    """String elements are coerced: int-like -> int, float-like -> float,
    'true'/'false' -> bool."""
    assert ch._unwrap_array(["8", "2.5", "true"]) == [8, 2.5, True]


def test_unwrap_array_nested_plain_dict_leaf_coerced() -> None:
    """Plain dict nested inside a list has its string-scalar leaves coerced."""
    assert ch._unwrap_array([{"a": "4", "b": "false"}]) == [{"a": 4, "b": False}]


def test_unwrap_hash_string_scalars_coerced() -> None:
    """String values in a plain hash are coerced to native types."""
    assert ch._unwrap_hash({"x": "10", "flag": "true"}) == {"x": 10, "flag": True}


def test_val_carried_container_unwraps_and_coerces() -> None:
    """A __Val__-carried value (a list here) is returned as-is after normalise;
    int elements pass through unchanged."""
    db = {"Parameters": [{"Name": "WS", "__Val__": [1, 2, 3]}]}
    assert ch._find_param(db, "WS") == [1, 2, 3]


# Pin D22b resolution: nested wrapper dicts pass through unchanged.
# _normalise_value does not detect sentinel keys inside a plain dict child,
# so the wrapper key is preserved as-is.  xml2json never emits nested wrappers;
# only hand-crafted JSON reaches this path.
def test_unwrap_hash_nested_wrapper_passes_through() -> None:
    """A nested __ArrayType__ wrapper inside _unwrap_hash is not unwrapped.

    The sentinel key passes through untouched -- this is the defined scope
    of the unwrap helpers (D22b resolution)."""
    result = ch._unwrap_hash({"d": {"__ArrayType__": [1, 2]}})
    assert result == {"d": {"__ArrayType__": [1, 2]}}
