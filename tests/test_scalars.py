"""Tests for the two scalar coercion rules in ``_scalars``: ``coerce_scalar``
(command-line values) and ``coerce_canonical`` (``genesispy-xml2json``)."""

from __future__ import annotations

import pytest

from genesispy._scalars import coerce_canonical, coerce_scalar


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("42", 42),
        ("-7", -7),
        ("+5", 5),
        ("0", 0),
        ("1.5", 1.5),
        (".5", 0.5),
        ("1.", 1.0),
        ("1e3", 1000.0),
        ("1.5E-2", 0.015),
        ("true", True),
        ("True", True),
        ("FALSE", False),
        ("hello", "hello"),
        ("", ""),
        ("   ", "   "),
        (42, 42),
        (3.14, 3.14),
        (True, True),
        (None, None),
    ],
)
def test_coerce_scalar_canonical(raw, expected):
    result = coerce_scalar(raw)
    assert result == expected
    assert type(result) is type(expected)


@pytest.mark.parametrize("raw", ["inf", "nan", "Infinity", "+inf", "-NaN"])
def test_coerce_scalar_inf_nan_round_trip_as_string(raw):
    """Stricter than ``float()``: inf/nan literals are kept as strings.

    Mirrors the previous ``json_io._coerce_scalar_str`` behaviour and
    tightens ``config_handler._coerce_scalar`` (which used to call
    ``float()`` unguarded and silently accept these tokens).
    """
    assert coerce_scalar(raw) == raw
    assert isinstance(coerce_scalar(raw), str)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("42", 42),
        ("-7", -7),
        ("0", 0),
        ("1.5", 1.5),
        ("-0.25", -0.25),
        ("true", True),
        ("false", False),
        # Not lossless: the text would not read back the same.
        ("010", "010"),
        ("+5", "+5"),
        ("1e3", "1e3"),
        (".5", ".5"),
        ("1.", "1."),
        ("True", "True"),
        ("hello", "hello"),
        ("", ""),
        (42, 42),
        (None, None),
    ],
)
def test_coerce_canonical(raw, expected):
    result = coerce_canonical(raw)
    assert result == expected
    assert type(result) is type(expected)


def test_command_line_values_use_the_permissive_rule():
    from genesispy.config_handler import _coerce_scalar as ch

    assert ch is coerce_scalar
