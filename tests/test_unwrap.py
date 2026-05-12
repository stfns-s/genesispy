"""Unit tests for config_handler unwrap helpers (JSON-native shape).

Verifies that ``_unwrap_array`` / ``_unwrap_hash`` / ``_find_param``
correctly handle the JSON-native shape used by genesispy core.
"""

from __future__ import annotations

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
