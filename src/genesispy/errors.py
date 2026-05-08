"""Genesis2py error hierarchy and reporting helpers.

Ported from Genesis2/PythonLibs/Genesis2/ErrorHandlers.py and the
``error`` / ``warning`` helpers from Manager.pm.
"""

from __future__ import annotations

import atexit
import sys
from typing import Optional

try:
    from colorama import Fore, Style, init as _colorama_init

    _colorama_init()
    _RED = Fore.RED
    _YELLOW = Fore.YELLOW
    _RESET = Style.RESET_ALL
except ImportError:  # pragma: no cover - colorama is in deps
    _RED = ""
    _YELLOW = ""
    _RESET = ""


_LOG_FH = None
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

    Pass ``None`` to disable. An atexit hook flushes the active log on
    shutdown so buffered writes survive abrupt exit.
    """
    global _LOG_FH, _ATEXIT_REGISTERED
    if _LOG_FH is not None:
        try:
            _LOG_FH.close()
        except Exception:
            pass
        _LOG_FH = None
    if path:
        _LOG_FH = open(path, "w", encoding="utf-8")
        if not _ATEXIT_REGISTERED:
            atexit.register(_close_log_at_exit)
            _ATEXIT_REGISTERED = True


def _log(msg: str) -> None:
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

    Writes a red ``ERROR:`` line to stderr.  When ``fatal`` is True (the
    default) raises ``cls`` (default ``GenesisPyError``); otherwise prints
    and returns. Pass a subclass (``ParseError``, ``ConfigError`` …) to
    preserve ``e.code`` discrimination at the call site.
    """
    sys.stderr.write(f"{_RED}\n\tERROR: {msg}\n\n{_RESET}")
    sys.stderr.flush()
    _log(f"\n\tERROR: {msg}\n\n")
    if fatal:
        raise cls(msg)


def warning(msg: str) -> None:
    """Report a warning to stderr in yellow."""
    sys.stderr.write(f"{_YELLOW}\n\tWARNING: {msg}\n\n{_RESET}")
    sys.stderr.flush()
    _log(f"\n\tWARNING: {msg}\n\n")
