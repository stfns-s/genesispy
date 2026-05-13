"""Cluster G: UniqueModule.to_string(*args).

Mirrors Perl ``to_string`` (UniqueModule.pm:2911): debug-print arbitrary
structures. Self-method only; no bare-name alias (matches Perl's
documented surface).
"""

from __future__ import annotations

import pytest

from genesispy import cache
from genesispy.reporting import ParameterError
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


class _Mod(UniqueModule):
    pass


def test_to_string_serialises_single_value() -> None:
    inst = _Mod(StubManager())
    s = inst.to_string([1, 2, 3])
    assert "[1, 2, 3]" in s


def test_to_string_serialises_multiple_values_newline_separated() -> None:
    inst = _Mod(StubManager())
    s = inst.to_string([1, 2], {"a": 1})
    lines = s.split("\n")
    assert len(lines) == 2
    assert "[1, 2]" in lines[0]
    assert "'a'" in lines[1]


def test_to_string_no_args_raises() -> None:
    inst = _Mod(StubManager())
    with pytest.raises(ParameterError, match="at least one argument"):
        inst.to_string()
