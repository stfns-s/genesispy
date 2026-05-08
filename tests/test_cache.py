"""Tests for genesispy.cache."""

from __future__ import annotations

from genesispy import cache


def setup_function(_fn) -> None:
    cache.clear_all()


def test_next_derivation_increments() -> None:
    assert cache.next_derivation("Foo") == 1
    assert cache.next_derivation("Foo") == 2
    assert cache.next_derivation("Bar") == 1
    assert cache.next_derivation("Foo") == 3


def test_clear_all_resets() -> None:
    cache.next_derivation("Foo")
    cache.OUTFILE_CONTENT_CACHE["a.v"] = "// hi"
    cache.MODULE_CACHE["x"] = object()  # type: ignore[assignment]
    cache.clear_all()
    assert cache.MODULE_NAME_NUM_DERIVS == {}
    assert cache.OUTFILE_CONTENT_CACHE == {}
    assert cache.MODULE_CACHE == {}


def test_outfile_content_cache_roundtrip() -> None:
    cache.OUTFILE_CONTENT_CACHE["foo.v"] = "module foo; endmodule"
    assert cache.OUTFILE_CONTENT_CACHE["foo.v"] == "module foo; endmodule"


def test_register_writes_module_cache() -> None:
    sentinel = object()
    cache.register("Foo_unq1", sentinel)  # type: ignore[arg-type]
    assert cache.MODULE_CACHE["Foo_unq1"] is sentinel
