"""Tests for genesispy.unique_module."""

from __future__ import annotations

import pytest

from genesispy import cache
from genesispy.unique_module import UniqueModule

from ._stubs import StubConfigHandler, StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


# ---------------------------------------------------------------- fixtures
class Top(UniqueModule):
    pass


class Leaf(UniqueModule):
    pass


# ---------------------------------------------------------------- root
def test_root_construction_and_module_name() -> None:
    mgr = StubManager()
    top = Top(mgr)
    assert top.get_module_name() == "Top"
    assert top.get_parent() is None
    assert top.get_top() is top


def test_to_verilog_banner_uses_manager_comment_prefix() -> None:
    mgr = StubManager()
    mgr.output_comment = "--"  # VHDL-style line comment
    top = Top(mgr)
    top.execute()
    out = top._outfile_handle.getvalue()
    # All banner lines must be prefixed with the configured comment.
    assert out.startswith("-- Genesis-Py generated module: Top")
    assert "// Genesis-Py" not in out


def test_to_verilog_banner_line_mode_default() -> None:
    """Line-mode banner uses output_comment prefix on every line."""
    mgr = StubManager()
    top = Top(mgr)
    top.define_param("N", default=8)
    top.execute()
    out = top._outfile_handle.getvalue()
    assert "// Genesis-Py generated module: Top" in out
    assert "// Source class: Top" in out
    assert "//   N = 8" in out


def test_to_verilog_banner_custom_line_prefix() -> None:
    """output_comment overrides the line prefix used in the banner."""
    mgr = StubManager()
    mgr.output_comment = "#"
    top = Top(mgr)
    top.define_param("N", default=8)
    top.execute()
    out = top._outfile_handle.getvalue()
    assert "# Genesis-Py generated module: Top" in out
    assert "# Source class: Top" in out
    assert "#   N = 8" in out
    assert "//" not in out


def test_to_verilog_banner_block_comment() -> None:
    """output_comment=(open, close) wraps the banner in a single block comment."""
    mgr = StubManager()
    mgr.output_comment = ("/*", "*/")
    top = Top(mgr)
    top.define_param("N", default=8)
    top.execute()
    out = top._outfile_handle.getvalue()
    lines = out.splitlines()
    assert lines[0] == "/*"
    assert " Genesis-Py generated module: Top" in out
    assert " Source class: Top" in out
    assert "   N = 8" in out
    assert lines[-1] == "*/"


# ---------------------------------------------------------------- params
def test_define_and_get_param() -> None:
    top = Top(StubManager())
    top.define_param("WIDTH", default=8, doc="bit width")
    assert top.get_param("WIDTH") == 8


def test_define_param_redefinition_raises() -> None:
    top = Top(StubManager())
    top.define_param("WIDTH", default=8)
    with pytest.raises(Exception):
        top.define_param("WIDTH", default=16)


def test_override_param() -> None:
    top = Top(StubManager())
    top.define_param("WIDTH", default=8)
    top.override_param("WIDTH", 32)
    assert top.get_param("WIDTH") == 32


def test_parameter_declarative_registers_and_returns_default() -> None:
    top = Top(StubManager())
    assert top.parameter("WIDTH", 8) == 8
    assert top.get_param("WIDTH") == 8


def test_parameter_consults_cfg_handler() -> None:
    cfg = StubConfigHandler({"WIDTH": 64})
    top = Top(StubManager(cfg_handler=cfg))
    assert top.parameter("WIDTH", 8) == 64
    assert top.get_param("WIDTH") == 64


from tests._stubs import make_cfg_manager as _real_cfg_manager  # noqa: E402


def test_hierarchical_cmdln_override_scoped_to_named_instance() -> None:
    mgr = _real_cfg_manager(["Top.u_a.WIDTH=64", "Top.u_b.WIDTH=128"])
    top = Top(mgr)
    a = top.unique_inst(Leaf, "u_a")
    b = top.unique_inst(Leaf, "u_b")
    c = top.unique_inst(Leaf, "u_c")
    assert a.parameter("WIDTH", 8) == 64
    assert b.parameter("WIDTH", 8) == 128
    # No matching scoped override -> default fires.
    assert c.parameter("WIDTH", 8) == 8


def test_unique_inst_kwarg_wins_over_hierarchical_cmdln_override() -> None:
    # Per Perl ConfigHandler.pm priority: GENERATE_PRIORITY > CMD_LINE.
    # In genesispy, unique_inst kwargs land in STATE_OVERRIDDEN before the
    # child runs, so parameter() short-circuits cfg_handler entirely.
    mgr = _real_cfg_manager(["Top.u_leaf.WIDTH=99"])
    top = Top(mgr)
    leaf = top.unique_inst(Leaf, "u_leaf", WIDTH=8)
    assert leaf.parameter("WIDTH", 1) == 8


# ---------------------------------------------------------------- hierarchy
def test_unique_inst_creates_child_with_parent() -> None:
    top = Top(StubManager())
    child = top.unique_inst(Leaf, "u_leaf", WIDTH=8)
    assert child.get_parent() is top
    assert child.get_instance_name() == "u_leaf"
    assert child.get_module_name() == "Leaf"


def test_unique_inst_dedup_reuses_unique_name() -> None:
    top = Top(StubManager())
    a = top.unique_inst(Leaf, "u_a", WIDTH=8)
    b = top.unique_inst(Leaf, "u_b", WIDTH=8)
    assert a.get_unique_module_name() == b.get_unique_module_name()
    # Different instance names, identical Verilog module name.
    assert a.get_instance_name() != b.get_instance_name()


def test_unique_inst_different_params_yields_different_unique_name() -> None:
    top = Top(StubManager())
    a = top.unique_inst(Leaf, "u_a", WIDTH=8)
    b = top.unique_inst(Leaf, "u_b", WIDTH=16)
    assert a.get_unique_module_name() != b.get_unique_module_name()


def test_unique_inst_param_encodes_params_in_name() -> None:
    top = Top(StubManager())
    a = top.unique_inst_param(Leaf, "u_a", WIDTH=8)
    assert "WIDTH" in a.get_unique_module_name()
    assert "8" in a.get_unique_module_name()


def test_no_module_cache_skips_writes() -> None:
    """`--no-module-cache` must gate writes, not just reads."""
    mgr = StubManager()
    mgr.no_module_cache = True
    top = Top(mgr)
    a = top.unique_inst(Leaf, "u_a", WIDTH=8)
    b = top.unique_inst(Leaf, "u_b", WIDTH=8)
    # Reads disabled → fresh module per call (different unique names).
    assert a.get_unique_module_name() != b.get_unique_module_name()
    # Writes disabled → no pre/post dedup keys in MODULE_CACHE.
    keys = list(cache.MODULE_CACHE)
    assert not any("::post::" in k for k in keys)
    # cache.register entries (keyed by unique name) still present so
    # synonym/clone resolution keeps working.
    assert any(a.get_unique_module_name() == k for k in keys)


def test_clone_outfile_handle_is_isolated() -> None:
    """Review10 #89: a clone must not share src's StringIO. Mutations on
    the clone (e.g. an unrelated emit during a test or future pinclude path)
    must not corrupt src's buffered Verilog."""
    top = Top(StubManager())
    src = top.unique_inst(Leaf, "u_src")
    clone = top.clone_inst(src, "u_clone")
    src.emit("// SRC content")
    clone.emit("// CLONE content")
    assert clone._outfile_handle is not src._outfile_handle
    assert "SRC" in src._outfile_handle.getvalue()
    assert "CLONE" in clone._outfile_handle.getvalue()
    assert "CLONE" not in src._outfile_handle.getvalue()
    assert "SRC" not in clone._outfile_handle.getvalue()


@pytest.mark.parametrize("method", ["unique_inst_param", "ununique_inst"])
def test_instantiation_does_not_cache_on_execute_failure(method: str) -> None:
    """A raising execute() must not poison MODULE_CACHE for either path."""

    class Boom(UniqueModule):
        calls = 0
        fail_first = True

        def execute(self) -> None:
            type(self).calls += 1
            if type(self).fail_first and type(self).calls == 1:
                raise RuntimeError("user code blew up")
            super().execute()

    top = Top(StubManager())
    instantiate = getattr(top, method)
    with pytest.raises(RuntimeError, match="user code blew up"):
        instantiate(Boom, "u_x", WIDTH=8)
    assert not any("Boom" in k for k in cache.MODULE_CACHE)

    Boom.fail_first = False
    child = instantiate(Boom, "u_x", WIDTH=8)
    assert Boom.calls == 2
    assert child.get_param("WIDTH") == 8


def test_unique_inst_post_dedup_rolls_back_synonym_side_effects() -> None:
    """Post-dedup must restore synonym caches the discarded child clobbered."""

    # Different pre-overrides ({} vs {WIDTH:8}), same eff_post -> post-dedup hit.
    class Foo(UniqueModule):
        def execute(self) -> None:
            self.parameter("WIDTH", 8)
            self.synonym("foo_alias")
            super().execute()

    top = Top(StubManager())
    a = top.unique_inst(Foo, "u_a")
    b = top.unique_inst(Foo, "u_b", WIDTH=8)
    assert b.get_unique_module_name() == a.get_unique_module_name()
    assert cache.MODULE_CACHE["foo_alias"] is a
    foo_keys = {
        k for k in cache.OUTFILE_CONTENT_CACHE if "Foo_unq" in k or "foo_alias" in k
    }
    assert foo_keys == {f"{a.get_unique_module_name()}.v", "foo_alias.v"}


def test_unique_inst_post_dedup_rolls_back_grandchild_registrations() -> None:
    """Post-dedup must clear grandchild registrations, not just direct synonyms.

    Discarded second Foo's nested ununique_inst(Bar, ...) would otherwise
    leave orphan Bar entries in MODULE_CACHE / OUTFILE_CONTENT_CACHE.
    (Post Cluster E: ununique_inst emits a bare ``Bar`` name on first call
    and aliases on a matching second call, so the second invocation never
    journals a separate write — but the rollback discipline still has to
    hold for the first one if Foo itself is post-dedup discarded.)
    """

    class Bar(UniqueModule):
        pass

    class Foo(UniqueModule):
        def execute(self) -> None:
            self.ununique_inst(Bar, "u_bar")
            self.parameter("WIDTH", 8)
            super().execute()

    top = Top(StubManager())
    a = top.unique_inst(Foo, "u_a")
    b = top.unique_inst(Foo, "u_b", WIDTH=8)
    # Same eff_post -> post-dedup hit on Foo.
    assert b.get_unique_module_name() == a.get_unique_module_name()
    bar_keys = [k for k in cache.MODULE_CACHE if k == "Bar" or k.startswith("Bar_unq")]
    assert len(bar_keys) == 1, f"orphan Bar registration: {bar_keys}"
    bar_outfiles = [
        k for k in cache.OUTFILE_CONTENT_CACHE
        if k == "Bar.v" or k.startswith("Bar_unq")
    ]
    assert len(bar_outfiles) == 1, f"orphan Bar outfile: {bar_outfiles}"


def test_clone_inst_shares_unique_module_name() -> None:
    top = Top(StubManager())
    src = top.unique_inst(Leaf, "u_src", WIDTH=8)
    clone = top.clone_inst(src, "u_clone")
    assert clone.get_unique_module_name() == src.get_unique_module_name()
    assert clone.get_instance_name() == "u_clone"
    # Perl parity: clone instance name must NOT be added to src's synonyms.
    # Synonyms fan out into extra cache entries via execute()/synonym();
    # clones are instance-level aliases only and own no Verilog file.
    assert "u_clone" not in src.get_synonyms()


def test_ununique_inst_preserves_bare_base_name_matching_params() -> None:
    """Post Cluster E: ununique_inst preserves the bare base name and
    aliases identical-params follow-ups to the same emitted module
    (mirrors Perl UnUniquifiedModules behaviour in UniqueModule.pm:1610).
    """
    top = Top(StubManager())
    a = top.ununique_inst(Leaf, "u_a", WIDTH=8)
    b = top.ununique_inst(Leaf, "u_b", WIDTH=8)
    assert a.get_unique_module_name() == "Leaf"
    assert b.get_unique_module_name() == "Leaf"


# ---------------------------------------------------------------- emit/exec
def test_emit_and_execute_populate_outfile_cache() -> None:
    top = Top(StubManager())
    child = top.unique_inst(Leaf, "u_leaf", WIDTH=8)
    fname = f"{child.get_unique_module_name()}.v"
    assert fname in cache.OUTFILE_CONTENT_CACHE
    body = cache.OUTFILE_CONTENT_CACHE[fname]
    assert "Genesis-Py generated module" in body
    assert child.get_unique_module_name() in body


def test_emit_appends_newline() -> None:
    top = Top(StubManager())
    top.emit("hello")
    top.emit("world")
    assert top._outfile_handle.getvalue() == "hello\nworld\n"


# ---------------------------------------------------------------- path
def test_get_instance_path_three_levels() -> None:
    class A(UniqueModule):
        pass

    class B(UniqueModule):
        pass

    class C(UniqueModule):
        pass

    top = A(StubManager())
    top._instance_name = "a"
    mid = top.unique_inst(B, "b")
    leaf = mid.unique_inst(C, "c")
    assert leaf.get_instance_path() == "a/b/c"


# ---------------------------------------- product-list / synth-top tagging
def _build_two_level_tree():
    """_TopHelper has two children: 'm' (under synth_top='top.m') and 'tb'."""
    class _TopHelper(UniqueModule):
        pass

    class Mid(UniqueModule):
        pass

    class Tb(UniqueModule):
        pass

    top = _TopHelper(StubManager())
    top._instance_name = "top"
    top.unique_inst(Mid, "m")
    top.unique_inst(Tb, "tb")
    return top


def test_get_prod_list_insts_no_synth_top_tags_everything_verif() -> None:
    top = _build_two_level_tree()
    pairs = top.get_prod_list_insts(None)
    assert {is_synth for _, is_synth in pairs} == {False}
    assert top in [inst for inst, _ in pairs]


def test_get_prod_list_insts_synth_top_root_tags_everything_synth() -> None:
    top = _build_two_level_tree()
    pairs = top.get_prod_list_insts("top")
    assert {is_synth for _, is_synth in pairs} == {True}


def test_get_prod_list_insts_synthtop_into_cloned_subtree() -> None:
    """Bug #1: --synthtop targeting a path under a clone must reach the
    source's descendants. Before the fix, the clone has empty
    `_sub_instances` and traversal stops short."""

    class _Leaf(UniqueModule):
        def execute(self):
            self.emit("// leaf body\n")
            super().execute()

    class _Mid(UniqueModule):
        def execute(self):
            self.ununique_inst(_Leaf, "u_leaf")
            super().execute()

    class _TopHelper(UniqueModule):
        pass

    top = _TopHelper(StubManager())
    top._instance_name = "top"
    # First Mid: canonical, executes, registers "_Leaf_unq*" in cache.
    top.unique_inst(_Mid, "u_mid1")
    # Second Mid: cache hit -> returns a clone of u_mid1 with empty
    # _sub_instances; clone reuses u_mid1's _Mid_unq* file.
    u_mid2 = top.unique_inst(_Mid, "u_mid2")
    assert u_mid2._clone_of is not None, "u_mid2 should be a clone for this scenario"

    # Without the fix, traversal of u_mid2 walks no descendants, so the
    # leaf's outfile is missing from the synth set when --synthtop targets
    # the cloned subtree.
    pairs = top.get_prod_list_insts("top.u_mid2.u_leaf")
    leaf_canonical = u_mid2._clone_of._sub_instances["u_leaf"]
    leaf_outfile = leaf_canonical._outfile_name
    assert leaf_outfile is not None
    synth_outfiles = {
        inst._outfile_name for inst, is_synth in pairs
        if is_synth and inst._outfile_name
    }
    assert leaf_outfile in synth_outfiles, (
        f"--synthtop into cloned subtree missed leaf {leaf_outfile!r}; "
        f"got {synth_outfiles!r}"
    )


def test_get_prod_list_insts_synth_top_midpoint_splits_tree() -> None:
    top = _build_two_level_tree()
    pairs = top.get_prod_list_insts("top.m")
    by_name = {inst._instance_name: is_synth for inst, is_synth in pairs}
    assert by_name["m"] is True
    assert by_name["tb"] is False
    # The 'top' instance is *above* synth_top -> verif (Perl parity:
    # ancestors of synth_top are not themselves synth).
    assert by_name["top"] is False


def test_subtree_signature_discriminates_parents_with_different_descendants() -> None:
    # Same-class parents at different paths with *different* scoped overrides
    # must not collapse before descendants can observe their overrides.
    class Inner(UniqueModule):
        pass

    class Outer(UniqueModule):
        pass

    mgr = _real_cfg_manager([
        "Top.u_a.u_in.WIDTH=8",
        "Top.u_b.u_in.WIDTH=16",
    ])
    top = Top(mgr)
    a = top.unique_inst(Outer, "u_a")
    b = top.unique_inst(Outer, "u_b")

    # Different subtree overrides -> distinct unique module names.
    assert a.get_unique_module_name() != b.get_unique_module_name()

    # And each Outer sees the correct scoped value when it instantiates
    # an Inner: the scoped --parameter Top.u_a.u_in.WIDTH=8 reaches the
    # Inner under u_a, and Top.u_b.u_in.WIDTH=16 reaches the Inner under
    # u_b.
    in_a = a.unique_inst(Inner, "u_in")
    in_b = b.unique_inst(Inner, "u_in")
    assert in_a.parameter("WIDTH", 1) == 8
    assert in_b.parameter("WIDTH", 1) == 16


def test_subtree_signature_collapses_parents_with_identical_descendants() -> None:
    # Companion to the above: when two parents at different paths have
    # *structurally identical* subtree overrides (same relative path,
    # same name, same value), the subtree signature is equal after the
    # path-relative re-keying and the parents DO collapse onto one
    # cached unique module — the original Genesis2 dedup behaviour.
    class Inner(UniqueModule):
        pass

    class Outer(UniqueModule):
        pass

    mgr = _real_cfg_manager([
        "Top.u_a.u_in.WIDTH=8",
        "Top.u_b.u_in.WIDTH=8",
    ])
    top = Top(mgr)
    a = top.unique_inst(Outer, "u_a")
    b = top.unique_inst(Outer, "u_b")

    # Same subtree shape -> same unique module name (clone or identical).
    assert a.get_unique_module_name() == b.get_unique_module_name()


def test_unique_inst_rollback_restores_overwritten_outfile_entry() -> None:
    """Post-dedup rollback restores pre-existing entries, not just drops new ones."""
    class _Worker(UniqueModule):
        # Toggle: synonym only on the discarded second elaboration.
        synonym_target = ""

        def execute(self) -> None:
            super().execute()
            if type(self).synonym_target:
                self.synonym(type(self).synonym_target)

    top = Top(StubManager())
    cache.OUTFILE_CONTENT_CACHE["preseeded.v"] = "PRESEED"

    # First call primes the post-dedup cache without synonym.
    top.unique_inst(_Worker, "u1", WIDTH=8)
    assert cache.OUTFILE_CONTENT_CACHE["preseeded.v"] == "PRESEED"

    # Second call's discarded child synonyms("preseeded"); rollback must restore.
    _Worker.synonym_target = "preseeded"
    try:
        top.unique_inst(_Worker, "u2", WIDTH=8)
    finally:
        _Worker.synonym_target = ""
    assert cache.OUTFILE_CONTENT_CACHE["preseeded.v"] == "PRESEED"


# Review 11 #131 -- ununique_inst must apply scoped CLI overrides.
def test_ununique_inst_honours_scoped_cmdln_override() -> None:
    """A `--parameter top.child.X=2` scoped override must reach an
    `ununique_inst` descendant (parity with `unique_inst` /
    `unique_inst_param`, which already route through `_resolve_params`).
    """
    class _ScopedCfg(StubConfigHandler):
        def cmdln_scoped_db_snapshot(self):
            return {(("top", "child"), "X"): {"value": 2}}

    observed: dict = {}

    class Child(UniqueModule):
        def execute(self):
            super().execute()
            self.define_param("X", default=1)
            observed["X"] = self.parameter("X")

    mgr = StubManager(cfg_handler=_ScopedCfg())
    top = Top(mgr)
    top._instance_name = "top"
    top.ununique_inst(Child, "child")
    assert observed["X"] == 2, (
        "scoped --parameter top.child.X=2 was ignored by ununique_inst"
    )
