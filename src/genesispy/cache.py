"""Process-wide singletons backing the elaboration engine.

These dictionaries replace the Perl ``shared-ref`` globals used in
``UniqueModule.pm`` (see e.g. lines 176-181, 248-251 of that file).  They
are intentionally module-level so that every ``UniqueModule`` instance
agrees on the dedup state.  Tests reset them via :func:`clear_all`.

The two journaled caches (MODULE_CACHE, OUTFILE_CONTENT_CACHE) record
writes inside an active :func:`journaled` block so :meth:`UniqueModule.unique_inst`
can roll back the discarded child's registrations on a post-elaboration
dedup hit without paying O(N) to copy/restore the entire cache.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Tuple

if TYPE_CHECKING:  # pragma: no cover
    from .unique_module import UniqueModule


_MISSING = object()


class _JournaledDict(dict):
    """``dict`` subclass that records first-touch writes for active journals.

    Each entry on :attr:`_journals` is a ``dict[key -> pre_value]`` capturing
    what the key was *before* the first write inside that journal scope; the
    sentinel :data:`_MISSING` means the key was absent. Rollback walks the
    journal and restores or deletes accordingly.

    Only ``__setitem__`` and ``__delitem__`` are journaled; ``.clear()`` is
    used only by :func:`clear_all` between tests and bypasses journaling on
    purpose. No call site uses ``.update()`` / ``.pop()`` / ``.popitem()``
    while a journal is active (verified at port time); add overrides if that
    changes.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._journals: List[Dict[Any, Any]] = []

    def _record(self, key: Any) -> None:
        if not self._journals:
            return
        prev = super().get(key, _MISSING)
        for j in self._journals:
            if key not in j:
                j[key] = prev

    def __setitem__(self, key: Any, value: Any) -> None:
        self._record(key)
        super().__setitem__(key, value)

    def __delitem__(self, key: Any) -> None:
        self._record(key)
        super().__delitem__(key)


# MODULE_CACHE keys live in two disjoint namespaces, partitioned by the
# `::` separator:
#   * dedup signatures used by unique_inst / unique_inst_param to collapse
#     equivalent elaborations:
#       "<base>::<sha256>"          (pre-elaboration param key)
#       "<base>::post::<sha256>"    (post-elaboration full-param key)
#       "<base>::param::<sha256>"   (parametric form)
#   * registered instance identifiers (`<base>_unqN`, plus user-supplied
#     synonyms) — these must NOT contain `::`; cache.register asserts this
#     so a future synonym name can never collide with a dedup signature.
MODULE_CACHE: _JournaledDict = _JournaledDict()

# Base-class-name -> next derivative counter.  Drives unique-name suffixes
# such as ``Foo_unq2``.
MODULE_NAME_NUM_DERIVS: Dict[str, int] = {}

# Filename -> emitted Verilog text.  Flushed on demand (e.g. by Manager).
OUTFILE_CONTENT_CACHE: _JournaledDict = _JournaledDict()

# Base-name -> {"instance": UniqueModule, "params": dict[str, Any]}.
# Tracks `ununique_inst` calls so a second call with the same base name
# either aliases the previously generated instance (identical resolved
# params) or raises (different params).  Mirrors Perl
# UnUniquifiedModules + does_generate_same (UniqueModule.pm:1610-1700);
# global scope (not per-parent) because the on-disk filename is global.
UNUNIQUE_REGISTRY: Dict[str, Dict[str, Any]] = {}


# Filename -> 'synth' | 'verif' | 'synth_and_verif'.  Built by Manager
# before flush from a path-based DFS over the elaborated instance tree
# (mirrors Perl Manager.pm:1330-1395 / UniqueModule.pm:_get_prod_list_insts).
# Empty when synth_top is None -> output_writer treats unmapped files as
# 'verif' (matches Perl SynthTop=undef default).
OUTFILE_TAGS: Dict[str, str] = {}


def clear_all() -> None:
    """Reset every singleton.  Intended for tests."""
    MODULE_CACHE.clear()
    MODULE_NAME_NUM_DERIVS.clear()
    OUTFILE_CONTENT_CACHE.clear()
    OUTFILE_TAGS.clear()
    UNUNIQUE_REGISTRY.clear()
    # Recycled tmpdir paths could otherwise inherit a stale .vpy mapping.
    from .template import runtime as _rt
    _rt.clear_line_maps()


def next_derivation(base_name: str) -> int:
    """Return the next derivative index for ``base_name`` (1-based).

    The first call returns ``1``; subsequent calls increment.  This
    matches the Perl ``ModuleNameNumDerivs`` semantics.

    Best-effort contiguous: gaps may appear when post-elaboration dedup
    in ``unique_inst`` reclaims a slot, and the rollback only fires if
    no nested ``next_derivation`` call bumped the counter past it.
    """
    n = MODULE_NAME_NUM_DERIVS.get(base_name, 0) + 1
    MODULE_NAME_NUM_DERIVS[base_name] = n
    return n


def register(unique_name: str, instance: "UniqueModule") -> None:
    """Register ``instance`` under ``unique_name`` in the module cache.

    Re-registering the same instance is a silent no-op. Re-registering a
    *different* instance under an existing name emits a one-line warning
    on stderr — typically a synonym collision or a misuse of
    `synonym_class`. The new entry still wins (preserves prior behaviour
    for tests that intentionally rebind), but the warning surfaces what
    used to be a silent overwrite.
    """
    if "::" in unique_name:
        # Reserved for dedup-signature keys; see module docstring.
        raise ValueError(
            f"cache.register: '::' is reserved in unique-name keys; "
            f"got {unique_name!r}"
        )
    existing = MODULE_CACHE.get(unique_name)
    if existing is not None and existing is not instance:
        from . import reporting

        reporting.warning(
            f"cache.register: {unique_name!r} already bound to a different "
            f"UniqueModule instance; overwriting."
        )
    MODULE_CACHE[unique_name] = instance


@contextmanager
def journaled() -> Iterator[Tuple[Dict[Any, Any], Dict[Any, Any]]]:
    """Context manager: capture writes to MODULE_CACHE and OUTFILE_CONTENT_CACHE.

    Yields a ``(mc_journal, oc_journal)`` pair of dicts that map each
    touched key to its pre-block value (or :data:`_MISSING` if absent at
    block entry). Pass these to :func:`rollback_journal` to undo only the
    writes recorded inside the block, leaving unrelated entries untouched.
    Journals nest: each scope tracks its own first-touch set.
    """
    mc_j: Dict[Any, Any] = {}
    oc_j: Dict[Any, Any] = {}
    MODULE_CACHE._journals.append(mc_j)
    OUTFILE_CONTENT_CACHE._journals.append(oc_j)
    try:
        yield mc_j, oc_j
    finally:
        OUTFILE_CONTENT_CACHE._journals.pop()
        MODULE_CACHE._journals.pop()


def rollback_journal(
    mc_j: Dict[Any, Any], oc_j: Dict[Any, Any]
) -> None:
    """Undo writes recorded by a :func:`journaled` block on both caches."""
    for key, prev in mc_j.items():
        if prev is _MISSING:
            dict.pop(MODULE_CACHE, key, None)
        else:
            dict.__setitem__(MODULE_CACHE, key, prev)
    for key, prev in oc_j.items():
        if prev is _MISSING:
            dict.pop(OUTFILE_CONTENT_CACHE, key, None)
        else:
            dict.__setitem__(OUTFILE_CONTENT_CACHE, key, prev)
