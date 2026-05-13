"""Regression tests for clone_inst / synonym / dedup semantics.

References (Genesis2/PerlLibs/Genesis2/UniqueModule.pm):

* ``clone_inst``  ~ line 1480 -- emits no per-clone file; the clone is
  purely an instance-level alias of the source's UniqueModuleName.
* ``new_as_clone`` ~ line 269 -- shares the source's OutfileHandle/Name.
* ``synonym``     ~ line 1724 -- alternate filename for the same content.
"""

from __future__ import annotations

import pytest

from genesispy import cache
from genesispy.reporting import ElaborationError
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


class _Top(UniqueModule):
    pass


class _Leaf(UniqueModule):
    pass


def test_clone_inst_emits_no_per_clone_file() -> None:
    """Perl parity: clone_inst is an instance-level alias only.

    The parent module's Verilog instantiates the clone using the source's
    UniqueModuleName; no additional ``<clone_instance_name>.v`` file is
    written to OUTFILE_CONTENT_CACHE.
    """
    top = _Top(StubManager())
    src = top.unique_inst(_Leaf, "u_src", WIDTH=8)
    clone = top.clone_inst(src, "u_clone")

    src_file = f"{src.get_unique_module_name()}.v"
    assert src_file in cache.OUTFILE_CONTENT_CACHE
    clone_file = f"{clone.get_instance_name()}.v"
    assert clone_file not in cache.OUTFILE_CONTENT_CACHE


def test_synonym_after_execute_publishes_outfile() -> None:
    top = _Top(StubManager())
    leaf = top.unique_inst(_Leaf, "u_leaf", WIDTH=8)
    leaf.synonym("LeafAlt")
    assert "LeafAlt.v" in cache.OUTFILE_CONTENT_CACHE
    src_file = f"{leaf.get_unique_module_name()}.v"
    assert (
        cache.OUTFILE_CONTENT_CACHE["LeafAlt.v"]
        == cache.OUTFILE_CONTENT_CACHE[src_file]
    )


class _LeafWithDefault(UniqueModule):
    """Leaf with an internal default; calling without WIDTH should be
    equivalent to passing WIDTH=8."""

    def execute(self) -> None:  # type: ignore[override]
        self.parameter("WIDTH", 8)
        super().execute()


class _Mid(UniqueModule):
    pass


def test_clone_inst_rejects_antecessor_cycle() -> None:
    """Perl parity (UniqueModule.pm:1521): cloning self or any ancestor
    must raise rather than silently producing a hierarchy cycle."""
    top = _Top(StubManager())
    mid = top.unique_inst(_Mid, "u_mid")

    with pytest.raises(ElaborationError) as excinfo:
        mid.clone_inst(top, "u_loop")

    msg = str(excinfo.value)
    assert "antecessor" in msg
    assert top.get_instance_path() in msg


def test_clone_inst_rejects_self_clone() -> None:
    """Cloning self is the degenerate antecessor case; must also raise."""
    top = _Top(StubManager())
    with pytest.raises(ElaborationError):
        top.clone_inst(top, "u_self")


def test_unique_inst_dedup_via_default_vs_explicit() -> None:
    top = _Top(StubManager())
    a = top.unique_inst(_LeafWithDefault, "u_a")          # no override
    b = top.unique_inst(_LeafWithDefault, "u_b", WIDTH=8)  # explicit, same value
    assert a.get_unique_module_name() == b.get_unique_module_name()


# ----------------------------------------------------- Cluster E: ununique_inst


def test_ununique_inst_preserves_bare_base_name() -> None:
    """First ununique_inst('Leaf', ...) emits 'Leaf', not 'Leaf_unq1'.

    Mirrors Perl ``ununique_inst`` (UniqueModule.pm:1545): the whole
    point is to keep the bare base name so PNR/synthesis tools can
    swap the module out for a macro.
    """
    top = _Top(StubManager())
    inst = top.ununique_inst(_Leaf, "u_analog", WIDTH=8)

    assert inst.get_unique_module_name() == "_Leaf"
    assert f"{_Leaf.__name__}.v" in cache.OUTFILE_CONTENT_CACHE
    # No _unqN file should be emitted.
    assert "_Leaf_unq1.v" not in cache.OUTFILE_CONTENT_CACHE


def test_ununique_inst_second_call_matching_params_aliases() -> None:
    """Second call with identical resolved params aliases the first instance.

    Both instances share the same _unique_module_name (the bare base).
    """
    top = _Top(StubManager())
    a = top.ununique_inst(_Leaf, "u_a", WIDTH=8)
    b = top.ununique_inst(_Leaf, "u_b", WIDTH=8)

    assert a.get_unique_module_name() == b.get_unique_module_name() == "_Leaf"
    # Only one Verilog file written.
    keys = [k for k in cache.OUTFILE_CONTENT_CACHE if k.startswith("_Leaf")]
    assert keys == ["_Leaf.v"], keys


def test_ununique_inst_second_call_differing_params_raises() -> None:
    """Second call with different resolved params must raise (Perl parity).

    Per UniqueModule.pm:1660-1661: "Will generate two different
    UN-uniquified ... modules!"
    """
    top = _Top(StubManager())
    top.ununique_inst(_Leaf, "u_a", WIDTH=8)
    with pytest.raises(ElaborationError) as excinfo:
        top.ununique_inst(_Leaf, "u_b", WIDTH=16)
    msg = str(excinfo.value)
    assert "two different UN-uniquified" in msg
    assert "WIDTH" in msg


def test_ununique_inst_registers_in_cache() -> None:
    """The bare base name is registered in MODULE_CACHE so
    subsequent string-form resolves find it."""
    top = _Top(StubManager())
    top.ununique_inst(_Leaf, "u_analog", WIDTH=8)
    assert "_Leaf" in cache.MODULE_CACHE
