"""Tests for genesispy.cache."""

from __future__ import annotations

from genesispy import cache



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


def test_journal_rolls_back_ununique_registry() -> None:
    cache.UNUNIQUE_REGISTRY["keep"] = {"params": {}}
    with cache.journaled() as journals:
        cache.UNUNIQUE_REGISTRY["drop"] = {"params": {}}
        cache.UNUNIQUE_REGISTRY["keep"] = {"params": {"W": 1}}
        cache.rollback_journal(*journals)
    assert "drop" not in cache.UNUNIQUE_REGISTRY
    assert cache.UNUNIQUE_REGISTRY["keep"] == {"params": {}}


def test_journal_rolls_back_side_files() -> None:
    cache.SIDE_FILES["keep.rpt"] = {"writer": "a", "listed": True}
    assert len(cache._JOURNALED) == 4
    with cache.journaled() as journals:
        assert len(journals) == 4
        cache.SIDE_FILES["drop.rpt"] = {"writer": "b", "listed": True}
        cache.SIDE_FILES["keep.rpt"] = {"writer": "b", "listed": False}
        cache.rollback_journal(*journals)
    assert "drop.rpt" not in cache.SIDE_FILES
    assert cache.SIDE_FILES["keep.rpt"] == {"writer": "a", "listed": True}
