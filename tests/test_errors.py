"""Tests for genesispy.reporting."""

from __future__ import annotations

import pytest

from genesispy.reporting import (
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
    assert "error:" in captured.err


def test_error_non_fatal_prints(capsys):
    error("just a note", fatal=False)  # should not raise
    captured = capsys.readouterr()
    assert "just a note" in captured.err


def test_warning_prints_to_stderr(capsys):
    warning("careful")
    captured = capsys.readouterr()
    assert "careful" in captured.err
    assert "warning:" in captured.err
    assert captured.out == ""


# Review 11 #179 -- error(cls=...) must raise the chosen subclass with its code.
def test_error_dispatches_subclass_for_code(capsys):
    """`error("...", cls=ParseError)` must raise ParseError, preserving e.code."""
    from genesispy.reporting import error, ParseError

    with pytest.raises(ParseError) as ei:
        error("oops", cls=ParseError)
    assert ei.value.code == "parse_error"
    assert ei.value.msg == "oops"


# Doc-review E4 -- reporting.error() already writes to stderr before raising,
# so a top-level handler must not print the same message a second time.
def test_error_marks_raised_instance_reported():
    """The instance error() raises carries reported=True."""
    with pytest.raises(GenesisPyError) as ei:
        error("boom")
    assert ei.value.reported is True


def test_directly_raised_error_is_not_marked_reported():
    """An exception built at a `raise` site was never printed, so reported stays False."""
    assert GenesisPyError("boom").reported is False
    assert ParseError("boom").reported is False


def test_manager_execute_reports_a_vpy_error_once(tmp_path, capsys):
    """A .vpy body calling error() must produce exactly one `error:` line.

    Regression: reporting.error() writes the message to stderr and then
    raises; Manager.execute's handler called error(..., fatal=False) on the
    way out, printing the same text a second time. Elaboration is the path
    that reaches the handler with an already-reported exception -- most
    engine-side failures (e.g. Manager.find_file) `raise` directly and are
    still the handler's job to print.
    """
    import os

    from genesispy import cache, cli
    from genesispy.manager import Manager

    src = tmp_path / "boom.vpy"
    src.write_text("//; error('deliberate failure')\n", encoding="utf-8")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        cache.clear_all()
        args = cli.parse_args(["-i", str(src), "-t", "boom", "--log", "/dev/null"])
        rc = Manager(args).execute()
    finally:
        os.chdir(cwd)
        cache.clear_all()
    captured = capsys.readouterr()

    assert rc == 1
    assert captured.err.count("deliberate failure") == 1
    assert captured.err.count("error:") == 1


def test_manager_execute_still_reports_unreported_errors(tmp_path, capsys):
    """An exception raised directly (reported=False) is still printed once."""
    import os

    from genesispy import cli
    from genesispy.manager import Manager

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        args = cli.parse_args(["-i", "nosuch.vpy", "-t", "top", "--log", "/dev/null"])
        rc = Manager(args).execute()
    finally:
        os.chdir(cwd)
    captured = capsys.readouterr()

    assert rc == 1
    assert captured.err.count("nosuch.vpy") == 1
