"""Synthetic unit tests for build_variant_map + normalize (content-ranked variant identity).

These tests require no Perl installation -- all inputs are hand-crafted strings.
They verify:
  - Swapped wiring is detected with variant maps (was a bug with the old collapse path).
  - Correct wiring passes with variant maps.
  - Feed order does not affect the result.
  - Grandchild fixpoint: variants of Foo that differ only by which Bar they instantiate
    get distinct ranks after fixpoint refinement.
  - Sentinel __U? is assigned for referenced-but-undefined variants.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _parity_normalize import build_variant_map, normalize  # noqa: E402


# ---------------------------------------------------------------------------
# Shared synthetic Verilog bodies
# ---------------------------------------------------------------------------

# Two Foo variants with distinct widths (genesispy-style names).
_FOO_W2_BODY = """\
// Source class: Foo
// Parameters:
//   width = 2
module Foo_unq1 (input clk, output [1:0] out);
  assign out = 2'b00;
endmodule // Foo_unq1
"""

_FOO_W5_BODY = """\
// Source class: Foo
// Parameters:
//   width = 5
module Foo_unq2 (input clk, output [4:0] out);
  assign out = 5'b00000;
endmodule // Foo_unq2
"""

# Two Foo variants with distinct widths (Perl-style _KEY_VAL names).
_FOO_W2_BODY_PERL = """\
// Source template: Foo
// Parameter width = 2
module Foo_width_2 (input clk, output [1:0] out);
  assign out = 2'b00;
endmodule // Foo_width_2
"""

_FOO_W5_BODY_PERL = """\
// Source template: Foo
// Parameter width = 5
module Foo_width_5 (input clk, output [4:0] out);
  assign out = 5'b00000;
endmodule // Foo_width_5
"""

# Parent A (genesispy names): wires Foo_unq1 (width=2) as child1, Foo_unq2 (width=5) as child2.
_PARENT_A_BODY = """\
// Source class: parent
// Parameters:
module parent_unq1 (input clk);
  Foo_unq1 child1 (.clk(clk));
  Foo_unq2 child2 (.clk(clk));
endmodule // parent_unq1
"""

# Parent B (Perl names): wires Foo_width_5 as child1 (SWAPPED) and Foo_width_2 as child2 (SWAPPED).
_PARENT_B_SWAPPED_BODY = """\
// Source template: parent
// Parameter
module parent_style_flat (input clk);
  Foo_width_5 child1 (.clk(clk));
  Foo_width_2 child2 (.clk(clk));
endmodule // parent_style_flat
"""

# Parent B (Perl names): correct wiring -- Foo_width_2 as child1, Foo_width_5 as child2.
_PARENT_B_CORRECT_BODY = """\
// Source template: parent
// Parameter
module parent_style_flat (input clk);
  Foo_width_2 child1 (.clk(clk));
  Foo_width_5 child2 (.clk(clk));
endmodule // parent_style_flat
"""

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_swapped_wiring_detected() -> None:
    """With build_variant_map, swapped wiring is detected as non-equal.

    OLD behavior (normalize with variant_map=None): both parent files collapse
    all Foo variants to Foo__U, so parent_A and parent_B look identical.
    NEW behavior (build_variant_map then normalize with map): each Foo variant
    gets a rank based on its body content; swapped assignments produce different
    normalised parent bodies.
    """
    bases = {"Foo", "parent"}

    side_a_texts = {
        "Foo_unq1.v": _FOO_W2_BODY,
        "Foo_unq2.v": _FOO_W5_BODY,
        "parent_unq1.v": _PARENT_A_BODY,
    }
    side_b_texts = {
        "Foo_width_2.v": _FOO_W2_BODY_PERL,
        "Foo_width_5.v": _FOO_W5_BODY_PERL,
        "parent_style_flat.v": _PARENT_B_SWAPPED_BODY,
    }

    # Old behavior: both parents normalize equal (the bug).
    old_a = normalize(_PARENT_A_BODY, bases)
    old_b = normalize(_PARENT_B_SWAPPED_BODY, bases)
    assert old_a == old_b, (
        "Pre-condition: old normalize collapses swapped wiring to equal strings. "
        f"Got:\n  A: {old_a!r}\n  B: {old_b!r}"
    )

    # New behavior: build per-side maps; swapped wiring is distinguishable.
    map_a = build_variant_map(side_a_texts, bases)
    map_b = build_variant_map(side_b_texts, bases)

    norm_a = normalize(_PARENT_A_BODY, bases, map_a)
    norm_b = normalize(_PARENT_B_SWAPPED_BODY, bases, map_b)

    assert norm_a != norm_b, (
        "Expected swapped wiring to produce different normalised parents, but got equal:\n"
        f"  norm_a: {norm_a!r}\n  norm_b: {norm_b!r}"
    )


def test_correct_wiring_passes() -> None:
    """With build_variant_map, correctly wired parents normalise equal."""
    bases = {"Foo", "parent"}

    side_a_texts = {
        "Foo_unq1.v": _FOO_W2_BODY,
        "Foo_unq2.v": _FOO_W5_BODY,
        "parent_unq1.v": _PARENT_A_BODY,
    }
    side_b_texts = {
        "Foo_width_2.v": _FOO_W2_BODY_PERL,
        "Foo_width_5.v": _FOO_W5_BODY_PERL,
        "parent_style_flat.v": _PARENT_B_CORRECT_BODY,
    }

    map_a = build_variant_map(side_a_texts, bases)
    map_b = build_variant_map(side_b_texts, bases)

    norm_a = normalize(_PARENT_A_BODY, bases, map_a)
    norm_b = normalize(_PARENT_B_CORRECT_BODY, bases, map_b)

    assert norm_a == norm_b, (
        "Expected correctly wired parents to normalise equal.\n"
        f"  norm_a: {norm_a!r}\n  norm_b: {norm_b!r}"
    )


def test_order_independence() -> None:
    """Feed order for build_variant_map does not affect the result."""
    bases = {"Foo", "parent"}

    texts_fwd = {
        "Foo_width_2.v": _FOO_W2_BODY_PERL,
        "Foo_width_5.v": _FOO_W5_BODY_PERL,
        "parent_style_flat.v": _PARENT_B_CORRECT_BODY,
    }
    # Reversed insertion order (Python dicts preserve insertion order).
    texts_rev = {
        "parent_style_flat.v": _PARENT_B_CORRECT_BODY,
        "Foo_width_5.v": _FOO_W5_BODY_PERL,
        "Foo_width_2.v": _FOO_W2_BODY_PERL,
    }

    side_a_texts = {
        "Foo_unq1.v": _FOO_W2_BODY,
        "Foo_unq2.v": _FOO_W5_BODY,
        "parent_unq1.v": _PARENT_A_BODY,
    }
    map_a = build_variant_map(side_a_texts, bases)
    map_fwd = build_variant_map(texts_fwd, bases)
    map_rev = build_variant_map(texts_rev, bases)

    norm_fwd = normalize(_PARENT_B_CORRECT_BODY, bases, map_fwd)
    norm_rev = normalize(_PARENT_B_CORRECT_BODY, bases, map_rev)
    norm_a = normalize(_PARENT_A_BODY, bases, map_a)

    assert norm_fwd == norm_rev, (
        "Feed order changed the normalised result.\n"
        f"  fwd: {norm_fwd!r}\n  rev: {norm_rev!r}"
    )
    assert norm_fwd == norm_a, (
        "Reversed-order map gives a different result from side A.\n"
        f"  fwd: {norm_fwd!r}\n  a:   {norm_a!r}"
    )


# ---------------------------------------------------------------------------
# Grandchild fixpoint test
# ---------------------------------------------------------------------------

_BAR_V1_BODY = """\
// Source class: Bar
// Parameters:
//   depth = 4
module Bar_unq1 (input clk);
  assign unused = 1'b0;
endmodule // Bar_unq1
"""

_BAR_V2_BODY = """\
// Source class: Bar
// Parameters:
//   depth = 8
module Bar_unq2 (input clk);
  assign unused = 1'b1;
endmodule // Bar_unq2
"""

_FOO_INST_BAR1_BODY = """\
// Source class: Foo
// Parameters:
//   width = 2
module Foo_unq1 (input clk);
  Bar_unq1 bar_i (.clk(clk));
endmodule // Foo_unq1
"""

_FOO_INST_BAR2_BODY = """\
// Source class: Foo
// Parameters:
//   width = 5
module Foo_unq2 (input clk);
  Bar_unq2 bar_i (.clk(clk));
endmodule // Foo_unq2
"""


def test_fixpoint_grandchild() -> None:
    """Fixpoint assigns distinct ranks to Foo variants that differ by Bar child.

    After one fixpoint round the Bar variants get distinct ranks; then the Foo
    variants (which each reference a different Bar rank) also get distinct ranks.
    Without fixpoint both Foo variants would have the same initial collapsed body
    (Bar_unq1 and Bar_unq2 both collapse to Bar__U initially before ranks exist).
    """
    bases = {"Foo", "Bar"}
    texts = {
        "Bar_unq1.v": _BAR_V1_BODY,
        "Bar_unq2.v": _BAR_V2_BODY,
        "Foo_unq1.v": _FOO_INST_BAR1_BODY,
        "Foo_unq2.v": _FOO_INST_BAR2_BODY,
    }

    vmap = build_variant_map(texts, bases)

    # Each Foo variant should get a distinct rank.
    foo_ranks = {vmap.get("Foo_unq1"), vmap.get("Foo_unq2")}
    assert None not in foo_ranks, f"Some Foo variant not in map: {vmap}"
    assert len(foo_ranks) == 2, (
        f"Expected 2 distinct Foo ranks after fixpoint, got: {foo_ranks}\nfull map: {vmap}"
    )

    # Each Bar variant should also get a distinct rank.
    bar_ranks = {vmap.get("Bar_unq1"), vmap.get("Bar_unq2")}
    assert None not in bar_ranks, f"Some Bar variant not in map: {vmap}"
    assert len(bar_ranks) == 2, (
        f"Expected 2 distinct Bar ranks after fixpoint, got: {bar_ranks}\nfull map: {vmap}"
    )


# ---------------------------------------------------------------------------
# Sentinel test
# ---------------------------------------------------------------------------


def test_sentinel_undefined_ref() -> None:
    """A referenced but undefined variant maps to <base>__U?."""
    bases = {"Foo"}
    texts = {
        "parent.v": """\
// Source class: parent
module parent_unq1 (input clk);
  Foo_unq99 child (.clk(clk));
endmodule
""",
    }

    vmap = build_variant_map(texts, bases)

    # Foo_unq99 is referenced but has no defining file.
    assert vmap.get("Foo_unq99") == "Foo__U?", (
        f"Expected Foo_unq99 -> 'Foo__U?', got {vmap.get('Foo_unq99')!r}\nfull map: {vmap}"
    )
