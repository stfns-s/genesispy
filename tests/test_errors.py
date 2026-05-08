"""Tests for genesispy.errors."""

from __future__ import annotations

import pytest

from genesispy.errors import (
    ConfigError,
    ElaborationError,
    GenesisPyError,
    ParameterError,
    ParseError,
    error,
    warning,
)


@pytest.mark.parametrize(
    "exc_cls",
    [GenesisPyError, ParseError, ConfigError, ParameterError, ElaborationError],
)
def test_exception_classes_raisable(exc_cls):
    with pytest.raises(exc_cls) as excinfo:
        raise exc_cls("boom")
    assert "boom" in str(excinfo.value)


def test_exception_with_location():
    e = GenesisPyError("oops", location="foo.vpy:42")
    assert "oops" in str(e)
    assert "foo.vpy:42" in str(e)


def test_exception_subclasses_are_genesispyerror():
    assert issubclass(ParseError, GenesisPyError)
    assert issubclass(ConfigError, GenesisPyError)
    assert issubclass(ParameterError, GenesisPyError)
    assert issubclass(ElaborationError, GenesisPyError)


@pytest.mark.parametrize(
    "exc_cls,expected_code",
    [
        (GenesisPyError, "genesispy_error"),
        (ParseError, "parse_error"),
        (ConfigError, "config_error"),
        (ParameterError, "parameter_error"),
        (ElaborationError, "elaboration_error"),
    ],
)
def test_exception_code_is_stable(exc_cls, expected_code):
    """Public ``code`` attribute is the stable identity for tests/handlers."""
    assert exc_cls.code == expected_code
    assert exc_cls("boom").code == expected_code


def test_error_fatal_raises(capsys):
    with pytest.raises(GenesisPyError):
        error("kaboom")
    captured = capsys.readouterr()
    assert "kaboom" in captured.err
    assert "ERROR" in captured.err


def test_error_non_fatal_prints(capsys):
    error("just a note", fatal=False)  # should not raise
    captured = capsys.readouterr()
    assert "just a note" in captured.err


def test_warning_prints_to_stderr(capsys):
    warning("careful")
    captured = capsys.readouterr()
    assert "careful" in captured.err
    assert "WARNING" in captured.err
    assert captured.out == ""


# Review 11 #179 -- error(cls=...) must raise the chosen subclass with its code.
def test_error_dispatches_subclass_for_code(capsys):
    """`error("...", cls=ParseError)` must raise ParseError, preserving e.code."""
    from genesispy.errors import error, ParseError

    with pytest.raises(ParseError) as ei:
        error("oops", cls=ParseError)
    assert ei.value.code == "parse_error"
    assert ei.value.msg == "oops"
