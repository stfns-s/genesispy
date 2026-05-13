"""Genesis2py reporting helpers and error hierarchy.

Ported from Genesis2/PythonLibs/Genesis2/ErrorHandlers.py and the
``error`` / ``warning`` helpers from Manager.pm.

The :func:`info`, :func:`warning`, and :func:`error` helpers write
cyan / yellow / red severity tags to stderr. Coloring is TTY-gated by
colorama: on POSIX, when stderr is not a tty (e.g. piped or redirected
to a file) the ANSI escapes are stripped. ``NO_COLOR`` is honored by
recent colorama versions. Every message is also teed through
:func:`_log` to the path set via :func:`set_log_file`, without color.
"""

from __future__ import annotations

import atexit
import os
import sys
from typing import Optional

_NO_COLOR = "NO_COLOR" in os.environ
try:
    from colorama import Fore, Style, init as _colorama_init

    _colorama_init()
    if _NO_COLOR:
        _RED = _YELLOW = _CYAN = _RESET = ""
    else:
        _RED = Fore.RED
        _YELLOW = Fore.YELLOW
        _CYAN = Fore.CYAN
        _RESET = Style.RESET_ALL
except ImportError:  # pragma: no cover - colorama is in deps
    _RED = ""
    _YELLOW = ""
    _CYAN = ""
    _RESET = ""


_LOG_FH = None
_LOG_PATH: Optional[str] = None
_ATEXIT_REGISTERED = False


def _close_log_at_exit() -> None:
    global _LOG_FH
    if _LOG_FH is not None:
        try:
            _LOG_FH.flush()
            _LOG_FH.close()
        except Exception:
            pass
        _LOG_FH = None


def set_log_file(path: Optional[str]) -> None:
    """Tee error/warning messages to ``path`` (in addition to stderr).

    Pass ``None`` to disable. The file is **lazy-opened** on the first
    error/warning so clean runs don't litter the workspace with empty
    log files (mirrors Perl's "log always available" promise without
    pre-creating). An atexit hook flushes the active log on shutdown so
    buffered writes survive abrupt exit.
    """
    global _LOG_FH, _LOG_PATH, _ATEXIT_REGISTERED
    if _LOG_FH is not None:
        try:
            _LOG_FH.close()
        except Exception:
            pass
        _LOG_FH = None
    _LOG_PATH = path
    if path and not _ATEXIT_REGISTERED:
        atexit.register(_close_log_at_exit)
        _ATEXIT_REGISTERED = True


def _log(msg: str) -> None:
    global _LOG_FH, _LOG_PATH
    if _LOG_FH is None and _LOG_PATH:
        try:
            _LOG_FH = open(_LOG_PATH, "w", encoding="utf-8")
        except Exception:
            # Couldn't open — disable logging silently; tee-to-stderr
            # in error()/warning() still surfaces the message.
            _LOG_PATH = None
            return
    if _LOG_FH is not None:
        try:
            _LOG_FH.write(msg)
            _LOG_FH.flush()
        except Exception:
            pass


class GenesisPyError(Exception):
    """Base class for genesispy exceptions.

    Optionally carries a ``location`` (e.g. file:line) appended to the
    message at format time. Subclasses set a stable ``code`` class
    attribute so tests can assert on identity rather than prose.
    """

    code: str = "genesispy_error"

    def __init__(self, msg: str = "", location: Optional[str] = None) -> None:
        self.msg = msg
        self.location = location
        super().__init__(self._format())

    def _format(self) -> str:
        if self.location:
            return f"{self.msg} (at {self.location})"
        return self.msg

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self._format()


class ParseError(GenesisPyError):
    """Raised for source/template parsing errors."""

    code = "parse_error"


class ConfigError(GenesisPyError):
    """Raised for configuration handling errors."""

    code = "config_error"


class ParameterError(GenesisPyError):
    """Raised for invalid module parameters."""

    code = "parameter_error"


class ElaborationError(GenesisPyError):
    """Raised for errors during hierarchy elaboration."""

    code = "elaboration_error"


def error(
    msg: str, *, fatal: bool = True, cls: type = GenesisPyError
) -> None:
    """Report an error.

    Writes a red ``error:`` line to stderr.  When ``fatal`` is True (the
    default) raises ``cls`` (default ``GenesisPyError``); otherwise prints
    and returns. Pass a subclass (``ParseError``, ``ConfigError`` …) to
    preserve ``e.code`` discrimination at the call site.
    """
    sys.stderr.write(f"{_RED}error:{_RESET} {msg}\n")
    sys.stderr.flush()
    _log(f"error: {msg}\n")
    if fatal:
        raise cls(msg)


def warning(msg: str) -> None:
    """Report a warning to stderr; the ``warning:`` tag is yellow."""
    sys.stderr.write(f"{_YELLOW}warning:{_RESET} {msg}\n")
    sys.stderr.flush()
    _log(f"warning: {msg}\n")


def info(msg: str) -> None:
    """Report an informational message to stderr; the ``info:`` tag is cyan."""
    sys.stderr.write(f"{_CYAN}info:{_RESET} {msg}\n")
    sys.stderr.flush()
    _log(f"info: {msg}\n")
