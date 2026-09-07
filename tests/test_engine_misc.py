"""Engine corners: --no-module-cache bypasses every registry; object params
never collide with string params in the dedup signature."""

from __future__ import annotations

from genesispy import hashing
from genesispy.unique_module import UniqueModule
from tests._stubs import StubManager


class _Top(UniqueModule):
    pass


class _Counting(UniqueModule):
    executions = 0

    def execute(self) -> None:
        super().execute()
        type(self).executions += 1


def test_no_module_cache_bypasses_the_ununique_registry() -> None:
    _Counting.executions = 0
    mgr = StubManager()
    mgr.no_module_cache = True
    top = _Top(mgr)
    for i in range(4):
        top.ununique_inst(_Counting, f"u{i}")
    assert _Counting.executions == 4


def test_cached_ununique_inst_aliases_after_the_first() -> None:
    _Counting.executions = 0
    top = _Top(StubManager())
    for i in range(4):
        top.ununique_inst(_Counting, f"u{i}")
    assert _Counting.executions == 1


def test_object_param_does_not_collide_with_equal_repr_string() -> None:
    class Obj:
        def __repr__(self) -> str:
            return "hello"

    a = hashing.sha256_param_signature("M", {"x": Obj()})
    b = hashing.sha256_param_signature("M", {"x": "hello"})
    assert a != b
