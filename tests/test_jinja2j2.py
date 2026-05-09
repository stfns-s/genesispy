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
