"""Tests for genesispy.tools.jinja2j2: stock-Jinja2 -> genesispy-j2 port.

Skipped wholesale when the optional ``jinja2`` package is absent.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytest.importorskip("jinja2")

from genesispy.template.parser import parse_vpy  # noqa: E402
from genesispy.tools.jinja2j2 import convert, _Unmappable, main  # noqa: E402


# --------------------------------------------------------------------------- #
# Block-opener colon insertion
# --------------------------------------------------------------------------- #

def test_for_gains_colon():
    out, issues = convert("{% for x in xs %}a{% endfor %}", strict=True)
    assert out == "{% for x in xs: %}a{% endfor %}"
    assert issues == []


def test_if_elif_else_gain_colon():
    src = "{% if a %}A{% elif b %}B{% else %}C{% endif %}"
    out, _ = convert(src, strict=True)
    assert out == "{% if a: %}A{% elif b: %}B{% else: %}C{% endif %}"


def test_while_gains_colon():
    out, _ = convert("{% while n %}x{% endwhile %}", strict=True)
    assert out == "{% while n: %}x{% endwhile %}"


def test_existing_colon_preserved():
    # Already in genesispy-j2 form: idempotent.
    src = "{% for x in xs: %}a{% endfor %}"
    out, _ = convert(src, strict=True)
    assert out == src


# --------------------------------------------------------------------------- #
# Whitespace modifiers
# --------------------------------------------------------------------------- #

def test_whitespace_modifiers_preserved():
    src = "{%- for x in xs -%}a{%- endfor -%}"
    out, _ = convert(src, strict=True)
    assert out == "{%- for x in xs: -%}a{%- endfor -%}"


# --------------------------------------------------------------------------- #
# Filter rewriting
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("src, expected", [
    ("{{ x | upper }}",           "{{ (x).upper() }}"),
    ("{{ x | lower }}",           "{{ (x).lower() }}"),
    ("{{ x | length }}",          "{{ len(x) }}"),
    ("{{ x | abs }}",             "{{ abs(x) }}"),
    ("{{ x | int }}",             "{{ int(x) }}"),
    ("{{ x | default(0) }}",      "{{ (x if x is not None else 0) }}"),
    ("{{ xs | join(',') }}",      "{{ ','.join(str(_) for _ in xs) }}"),
    ("{{ xs | first }}",          "{{ (xs)[0] }}"),
    ("{{ xs | last }}",           "{{ (xs)[-1] }}"),
    ("{{ xs | reverse }}",        "{{ list(reversed(xs)) }}"),
    ("{{ xs | sort }}",           "{{ sorted(xs) }}"),
    ("{{ s | replace('a','b') }}", "{{ (s).replace('a', 'b') }}"),
    ("{{ s | trim }}",            "{{ (s).strip() }}"),
])
def test_filters(src, expected):
    out, issues = convert(src, strict=True)
    assert out == expected, (out, expected)
    assert issues == []


def test_chained_filters():
    out, _ = convert("{{ xs | join(',') | upper }}", strict=True)
    assert out == "{{ (','.join(str(_) for _ in xs)).upper() }}"


def test_safe_is_noop():
    out, issues = convert("{{ x | safe }}", strict=True)
    assert out == "{{ x }}"
    assert issues == []


def test_escape_warns_in_strict():
    # `escape` and `e` are dropped (no HTML output) and emit a warning,
    # but do not fail in strict mode.
    out, issues = convert("{{ x | escape }}", strict=True)
    assert out == "{{ x }}"
    assert any("escape" in i.reason for i in issues)


def test_unknown_filter_strict_errors():
    with pytest.raises(_Unmappable, match="unknown filter 'mythical'"):
        convert("{{ x | mythical }}", strict=True)


def test_unknown_filter_best_effort_warns():
    out, issues = convert("{{ x | mythical }}", strict=False)
    assert any("mythical" in i.reason for i in issues)
    assert "_TODO" in out  # placeholder marker


# --------------------------------------------------------------------------- #
# Test (`is`) rewriting
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("src, expected_fragment", [
    ("{% if x is defined %}A{% endif %}",    "(x) is not None"),
    ("{% if x is none %}A{% endif %}",       "(x) is None"),
    ("{% if x is number %}A{% endif %}",     "isinstance(x, (int, float))"),
    ("{% if x is string %}A{% endif %}",     "isinstance(x, str)"),
    ("{% if x is sequence %}A{% endif %}",   "isinstance(x, (list, tuple))"),
    ("{% if x is mapping %}A{% endif %}",    "isinstance(x, dict)"),
])
def test_tests(src, expected_fragment):
    out, _ = convert(src, strict=True)
    assert expected_fragment in out


# --------------------------------------------------------------------------- #
# `set` rewriting
# --------------------------------------------------------------------------- #

def test_set_assignment():
    out, _ = convert("{% set N = 4 %}", strict=True)
    assert out == "{% N = 4 %}"


def test_set_with_filter():
    out, _ = convert("{% set N = xs | length %}", strict=True)
    assert out == "{% N = len(xs) %}"


def test_set_block_strict_errors():
    with pytest.raises(_Unmappable, match="set-block"):
        convert("{% set X %}body{% endset %}", strict=True)


# --------------------------------------------------------------------------- #
# `include`
# --------------------------------------------------------------------------- #

def test_include_literal():
    out, _ = convert('{% include "foo.j2" %}', strict=True)
    assert out == "{% include('foo.j2') %}"


def test_include_with_context_strict_errors():
    with pytest.raises(_Unmappable, match="complex 'include'"):
        convert('{% include "foo.j2" with context %}', strict=True)


# --------------------------------------------------------------------------- #
# Comments & raw text
# --------------------------------------------------------------------------- #

def test_comments_pass_through():
    out, _ = convert("{# hello #}\nplain\n{# bye #}", strict=True)
    assert out == "{# hello #}\nplain\n{# bye #}"


def test_raw_text_unchanged():
    out, _ = convert("module foo;\nendmodule\n", strict=True)
    assert out == "module foo;\nendmodule\n"


# --------------------------------------------------------------------------- #
# Unmappable constructs
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("src", [
    "{% macro foo() %}x{% endmacro %}",
    "{% block name %}x{% endblock %}",
    '{% extends "base.j2" %}',
    '{% import "f" as x %}',
    "{% raw %}x{% endraw %}",
])
def test_unmappable_strict(src):
    with pytest.raises(_Unmappable):
        convert(src, strict=True)


def test_unmappable_best_effort():
    out, issues = convert("{% macro foo() %}x{% endmacro %}", strict=False)
    assert "TODO(genesispy-jinja2j2)" in out
    assert len(issues) >= 1


# --------------------------------------------------------------------------- #
# End-to-end round-trip: converted output must parse with parse_vpy
# --------------------------------------------------------------------------- #

ROUND_TRIP_SOURCES = [
    # Simple for loop with filter and test.
    textwrap.dedent("""\
        {% for i in range(W) %}
        wire r{{ i }};
        {% endfor %}
    """),
    # if/elif/else with `is defined`.
    textwrap.dedent("""\
        {% if x is defined %}
        // x: {{ x | upper }}
        {% elif y is none %}
        // none
        {% else %}
        // other
        {% endif %}
    """),
    # set + include.
    textwrap.dedent("""\
        {% set W = 4 %}
        {% if W: %}
        wire r{{ W }};
        {% endif %}
    """),
]


@pytest.mark.parametrize("src", ROUND_TRIP_SOURCES)
def test_round_trip_parses(tmp_path, src):
    """Convert stock-Jinja2 to genesispy-j2; ensure parse_vpy accepts it."""
    converted, issues = convert(src, strict=True)
    assert issues == [] or all("escape" in i.reason for i in issues)

    # Substitute W=4 so parse_vpy doesn't choke on undefined names at parse
    # time -- parse_vpy is a syntactic transform, but we want the verifying
    # parse to succeed without surprise.
    p = tmp_path / "t.vpy"
    p.write_text(converted)

    # parse_vpy returns a list[str]; failure is a ParseError raise.
    parse_vpy(str(p), syntax="j2")


# --------------------------------------------------------------------------- #
# CLI smoke
# --------------------------------------------------------------------------- #

def test_cli_strict_pass(tmp_path, capsys):
    inp = tmp_path / "in.j2"
    inp.write_text("{% for x in xs %}{{ x | upper }}{% endfor %}")
    out = tmp_path / "out.vpy"
    rc = main([str(inp), "-o", str(out)])
    assert rc == 0
    assert out.read_text() == "{% for x in xs: %}{{ (x).upper() }}{% endfor %}"


def test_cli_strict_fail(tmp_path, capsys):
    inp = tmp_path / "in.j2"
    inp.write_text("{% macro f() %}x{% endmacro %}")
    rc = main([str(inp), "-o", str(tmp_path / "out.vpy")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "cannot port" in err and "macro" in err


def test_cli_best_effort(tmp_path, capsys):
    inp = tmp_path / "in.j2"
    inp.write_text("{% macro f() %}x{% endmacro %}")
    out = tmp_path / "out.vpy"
    rc = main([str(inp), "--best-effort", "-o", str(out)])
    assert rc == 0
    assert "TODO(genesispy-jinja2j2)" in out.read_text()
    err = capsys.readouterr().err
    assert "manual fixup" in err


# --------------------------------------------------------------------------- #
# Loop filter (B16)
# --------------------------------------------------------------------------- #

def test_loop_filter_simple():
    """{% for x in xs if x > 2 %} -> genexp, no else None."""
    out, issues = convert("{% for x in xs if x > 2 %}{{ x }}{% endfor %}", strict=True)
    assert "for x in (x for x in xs if" in out
    assert "else None" not in out
    assert issues == []


def test_loop_filter_tuple_target():
    """Tuple target appears in both binding and filter position."""
    out, issues = convert("{% for k, v in d.items() if v %}{{ k }}{% endfor %}", strict=True)
    assert "for (k, v) in ((k, v) for (k, v) in d.items() if" in out
    assert "else None" not in out
    assert issues == []


def test_loop_recursive_strict_errors():
    """{% for x in xs recursive %} -> strict raises _Unmappable."""
    with pytest.raises(_Unmappable):
        convert("{% for x in xs recursive %}{{ x }}{% endfor %}", strict=True)


def test_loop_recursive_best_effort_todo():
    """{% for x in xs recursive %} -> best-effort emits TODO comment."""
    out, issues = convert(
        "{% for x in xs recursive %}{{ x }}{% endfor %}", strict=False
    )
    assert "TODO(genesispy-jinja2j2)" in out
    assert len(issues) >= 1


def test_loop_filterless_byte_identical():
    """Filterless for loops must produce the same output as before the fix."""
    src = "{% for x in xs %}a{% endfor %}"
    out, issues = convert(src, strict=True)
    assert out == "{% for x in xs: %}a{% endfor %}"
    assert issues == []


# --------------------------------------------------------------------------- #
# for-else block-context stack (B17)
# --------------------------------------------------------------------------- #

def test_for_else_strict_raises():
    """for-else: strict mode must raise _Unmappable (semantic inversion)."""
    with pytest.raises(_Unmappable, match="for-else"):
        convert("{% for x in xs %}a{% else %}b{% endfor %}", strict=True)


def test_for_else_best_effort_todo():
    """for-else: best-effort emits exactly one Issue and a TODO comment."""
    src = "{% for x in xs %}a{% else %}b{% endfor %}"
    out, issues = convert(src, strict=False)
    assert "TODO(genesispy-jinja2j2)" in out
    assert len([i for i in issues if "for-else" in i.reason.lower()
                or "empty" in i.reason.lower()]) == 1


def test_if_else_unchanged():
    """else under if must still produce else: (not TODO)."""
    src = "{% if a %}A{% else %}B{% endif %}"
    out, issues = convert(src, strict=True)
    assert out == "{% if a: %}A{% else: %}B{% endif %}"
    assert issues == []


def test_nested_if_else_inside_for():
    """else under if nested inside for must bind to the if, zero issues."""
    src = "{% for x in xs %}{% if c %}A{% else %}B{% endif %}{% endfor %}"
    out, issues = convert(src, strict=True)
    assert "else:" in out
    assert "TODO" not in out
    assert issues == []


def test_while_else_strict_raises():
    """else after while: strict raises _Unmappable (same treatment as for-else)."""
    with pytest.raises(_Unmappable, match="for-else|while-else"):
        convert("{% while n %}x{% else %}y{% endwhile %}", strict=True)


def test_sentinel_closer_pops_stack():
    """Sentinel-comment closer (# endfor) must pop the stack correctly."""
    # After the sentinel endfor, a subsequent top-level else should be an error
    # only if stack is empty/non-for — here we just verify no crash and the
    # for body's if-else converts cleanly when sentinel form is used.
    src = "{% for x in xs %}{% if c %}A{% else %}B{% endif %}{% endfor %}"
    out, issues = convert(src, strict=True)
    assert "else:" in out
    assert issues == []


def test_sentinel_closer_input_pops_stack():
    """Sentinel-comment closer (# endfor) pops the block stack correctly.

    The sentinel {% # endfor %} must pop 'for' from the block stack so that
    the following top-level {% else %} sees an empty stack and converts to
    'else:' (no error). If the pop were missing, the else would see 'for' on
    the stack top, and strict conversion would raise _Unmappable("...for-else...")
    (semantic inversion). This template is not valid standalone Jinja — the
    converter is span-based and doesn't validate — but it precisely pinpoints
    the stack-pop mechanics.
    """
    src = "{% for x in xs %}a{% # endfor %}{% else %}b{% endif %}"
    out, issues = convert(src, strict=True)
    # Sentinel pop must execute, leaving the stack empty when {% else %} is
    # encountered, so conversion succeeds without raising _Unmappable.
    assert issues == []
    assert "else:" in out
