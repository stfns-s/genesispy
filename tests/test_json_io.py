"""Tests for genesispy.json_io."""

from __future__ import annotations

import json

import pytest

from genesispy import json_io


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body)
    return str(p)


def test_read_json_top_level_dict_required(tmp_path):
    p = _write(tmp_path, "bad.json", "[1, 2, 3]")
    with pytest.raises(ValueError):
        json_io.read_json(p)


def test_read_json_basic(tmp_path):
    p = _write(
        tmp_path,
        "ok.json",
        json.dumps({"HierarchyTop": {"BaseModuleName": "top"}}),
    )
    assert json_io.read_json(p) == {"HierarchyTop": {"BaseModuleName": "top"}}


def test_read_json_missing_file():
    with pytest.raises(FileNotFoundError):
        json_io.read_json("/no/such/file.json")


def test_write_json_roundtrip_native(tmp_path):
    native = {
        "HierarchyTop": {
            "BaseModuleName": "top",
            "Parameters": [
                {"Name": "WIDTH", "__Val__": 8},
                {"Name": "WIDTHS", "__ArrayType__": [2, 5, 16]},
                {"Name": "CFG", "__HashType__": {"a": 1, "b": 2}},
            ],
        }
    }
    p = str(tmp_path / "out.json")
    json_io.write_json(native, p)
    assert json_io.read_json(p) == native


def test_write_json_native_strings_preserved(tmp_path):
    """JSON in / JSON out preserves author-typed strings (no coercion)."""
    native = {
        "HierarchyTop": {
            "Parameters": [
                {"Name": "WIDTH", "__Val__": "8"},
                {"Name": "FLAG", "__Val__": "true"},
            ]
        }
    }
    p = str(tmp_path / "json_native.json")
    json_io.write_json(native, p)
    assert json_io.read_json(p) == native


def test_write_json_utf8(tmp_path):
    """Non-ASCII string values must round-trip independent of locale."""
    native = {"Top": {"Note": "αβγ — δοκιμή", "__Val__": "λ"}}
    p = str(tmp_path / "utf8.json")
    json_io.write_json(native, p)
    with open(p, "rb") as fh:
        raw = fh.read()
    assert raw.decode("utf-8")
    assert json_io.read_json(p) == native


def test_write_json_rejects_text_keys(tmp_path):
    """Mixed XML text content (legacy `_text`) is not JSON-representable."""
    bad = {"Top": {"_text": "hello"}}
    p = str(tmp_path / "bad.json")
    with pytest.raises(ValueError, match="_text"):
        json_io.write_json(bad, p)


# Review 11 #174 -- _check_no_text must reject cycles cleanly, not RecursionError.
def test_write_json_rejects_cyclic_input(tmp_path):
    """A self-referential dict must surface as ValueError, not RecursionError."""
    d: dict = {}
    d["self"] = d
    p = str(tmp_path / "cycle.json")
    with pytest.raises(ValueError):
        json_io.write_json(d, p)
