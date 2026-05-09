"""Tests for parse_vpy(syntax='jinja2'): jinja2 delimiters with full-Python
semantics. Behaviour mirrors the genesis-mode parser; only delimiters change.
"""

from __future__ import annotations

import io
import os
import textwrap
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from genesispy.errors import ParseError
from genesispy.template.parser import parse_vpy


def _vpy(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "t.vpy"
    p.write_text(body)
    return p


def _exec_body(src: str, **bindings) -> str:
    """Compile + exec a parsed body with a stub `self` that captures
    self.emit("...") calls and returns the joined output."""
    captured: list[str] = []

    class _Self:
        def emit(self, line):
            captured.append(line)

    # Wrap as a function so 'self' is a parameter.
    wrapped = "def _exec(self):\n" + "\n".join(
        ("    " + ln if ln.strip() else "") for ln in src.splitlines()
    ) + "\n"
    ns: dict = dict(bindings)
    code = compile(wrapped, "<test>", "exec")
    exec(code, ns)
    ns["_exec"](_Self())
    return "\n".join(captured)


# ---------------------------------------------------------------------------
# Single-line directive forms
# ---------------------------------------------------------------------------

def test_plain_text_passthrough(tmp_path):
    p = _vpy(tmp_path, "module foo;\nendmodule\n")
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    assert out == "module foo;\nendmodule"


def test_inline_expression(tmp_path):
    p = _vpy(tmp_path, "wire [{{ N - 1 }}:0] foo;\n")
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"), N=8)
    assert out == "wire [7:0] foo;"


def test_directive_assignment_and_use(tmp_path):
    p = _vpy(tmp_path, "{% N = 4 %}\nwire [{{ N - 1 }}:0] foo;\n")
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    assert out == "wire [3:0] foo;"


def test_for_loop_with_sentinel_close(tmp_path):
    src = textwrap.dedent("""\
        {% for i in range(3): %}
        foo[{{ i }}]
        {% # endfor %}
        """)
    p = _vpy(tmp_path, src)
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    assert out == "foo[0]\nfoo[1]\nfoo[2]"


def test_if_else(tmp_path):
    src = textwrap.dedent("""\
        {% if N > 0: %}
        big
        {% else: %}
        zero
        {% # endif %}
        """)
    p = _vpy(tmp_path, src)
    assert _exec_body(parse_vpy(str(p), syntax="jinja2"), N=1) == "big"
    assert _exec_body(parse_vpy(str(p), syntax="jinja2"), N=0) == "zero"


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def test_comment_whole_line_acts_like_blank(tmp_path):
    p = _vpy(tmp_path, "before\n{# this is a comment #}\nafter\n")
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    # Whole-line comment behaves like a blank input line: emit("").
    assert out == "before\n\nafter"


def test_comment_inline_stripped(tmp_path):
    p = _vpy(tmp_path, "x = {{ 1 }} {# c #} y\n")
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    assert out == "x = 1  y"


def test_comment_multiline_consumes_lines(tmp_path):
    src = "before\n{# multi\nline comment\nspans #}after\n"
    p = _vpy(tmp_path, src)
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    # The two intervening lines inside the comment are consumed; the closer
    # line picks up "after" as its plain text.
    assert out == "before\nafter"


# ---------------------------------------------------------------------------
# Multi-line forms
# ---------------------------------------------------------------------------

def test_multiline_directive_parenthesised(tmp_path):
    src = textwrap.dedent("""\
        {% foo = (
            1 + 2 +
            3
        ) %}
        x = {{ foo }}
        """)
    p = _vpy(tmp_path, src)
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    assert out == "x = 6"


def test_multiline_expression(tmp_path):
    src = "wire [{{ N\n  - 1 }}:0] x;\n"
    p = _vpy(tmp_path, src)
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"), N=8)
    assert out == "wire [7:0] x;"


# ---------------------------------------------------------------------------
# Whitespace modifiers (no-op)
# ---------------------------------------------------------------------------

def test_dash_modifiers_noop(tmp_path):
    src_a = "{%- N = 4 -%}\n{{- N -}}\n"
    src_b = "{% N = 4 %}\n{{ N }}\n"
    pa = tmp_path / "a.vpy"
    pa.write_text(src_a)
    pb = tmp_path / "b.vpy"
    pb.write_text(src_b)
    out_a = _exec_body(parse_vpy(str(pa), syntax="jinja2"))
    out_b = _exec_body(parse_vpy(str(pb), syntax="jinja2"))
    assert out_a == out_b == "4"


# ---------------------------------------------------------------------------
# Full-Python expressions inside {{ ... }}
# ---------------------------------------------------------------------------

def test_dict_literal_in_expr(tmp_path):
    p = _vpy(tmp_path, "{{ {0: 'a', 1: 'b'}[k] }}\n")
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"), k=1)
    assert out == "b"


def test_fstring_in_expr(tmp_path):
    p = _vpy(tmp_path, "{{ f'x={x}' }}\n")
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"), x=42)
    assert out == "x=42"


def test_brace_escape_in_text(tmp_path):
    # `\{{` is a literal `{{` in plain text.
    p = _vpy(tmp_path, r"x = \{{ literal" + "\n")
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    assert out == "x = {{ literal"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_unterminated_directive(tmp_path):
    p = _vpy(tmp_path, "{% x = 1\n")
    with pytest.raises(ParseError, match="unterminated"):
        parse_vpy(str(p), syntax="jinja2")


def test_unterminated_expression(tmp_path):
    p = _vpy(tmp_path, "x = {{ 1 + 2\n")
    with pytest.raises(ParseError, match="unterminated"):
        parse_vpy(str(p), syntax="jinja2")


def test_unterminated_comment(tmp_path):
    p = _vpy(tmp_path, "x = {# stuff\n")
    with pytest.raises(ParseError, match="unterminated"):
        parse_vpy(str(p), syntax="jinja2")


def test_directive_must_start_line(tmp_path):
    p = _vpy(tmp_path, "x = 1 {% y = 2 %}\n")
    with pytest.raises(ParseError) as exc:
        parse_vpy(str(p), syntax="jinja2")
    msg = str(exc.value)
    assert "must start the line" in msg
    # Distinguish from the must-end-the-line error: a buggy parser that
    # raised both messages on every input would still match the first
    # substring; require this error not also bear the other path's hint.
    assert "must end the line" not in msg


def test_directive_must_end_line(tmp_path):
    p = _vpy(tmp_path, "{% x = 1 %} trailing\n")
    with pytest.raises(ParseError) as exc:
        parse_vpy(str(p), syntax="jinja2")
    msg = str(exc.value)
    assert "must end the line" in msg
    assert "must start the line" not in msg


def test_misaligned_directive_indent(tmp_path):
    # 3 spaces inside the directive (after one optional drop) is not a
    # multiple of 4.
    p = _vpy(tmp_path, "{%    x = 1 %}\n")
    # 4 spaces -> py_indent=1: this should NOT raise. Test misalignment:
    p = _vpy(tmp_path, "{%   x = 1 %}\n")  # 3 spaces inside (after the leading-space-drop, 2)
    with pytest.raises(ParseError, match="misaligned"):
        parse_vpy(str(p), syntax="jinja2")


def test_tab_in_directive_indent(tmp_path):
    p = _vpy(tmp_path, "{%\tx = 1 %}\n")
    with pytest.raises(ParseError, match="tab character"):
        parse_vpy(str(p), syntax="jinja2")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def test_unknown_syntax_raises(tmp_path):
    p = _vpy(tmp_path, "module foo;\n")
    with pytest.raises(ValueError, match="unknown syntax"):
        parse_vpy(str(p), syntax="bogus")


def test_genesis_default_unchanged(tmp_path):
    """Default syntax='genesis' gives the same output as before."""
    p = _vpy(tmp_path, "//; for i in range(2):\nfoo[`i`]\n//; # endfor\n")
    out = _exec_body(parse_vpy(str(p)))  # default
    assert out == "foo[0]\nfoo[1]"


# ---------------------------------------------------------------------------
# Round-trip equivalence: same logic in both flavours produces same output.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Bare end-keyword block close ({% endfor %} / {% endif %} / {% endwhile %})
# ---------------------------------------------------------------------------

def test_for_loop_with_bare_endfor(tmp_path):
    src = textwrap.dedent("""\
        {% for i in range(3): %}
        foo[{{ i }}]
        {% endfor %}
        """)
    p = _vpy(tmp_path, src)
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    assert out == "foo[0]\nfoo[1]\nfoo[2]"


def test_if_with_bare_endif(tmp_path):
    src = textwrap.dedent("""\
        {% if N > 0: %}
        big
        {% endif %}
        """)
    p = _vpy(tmp_path, src)
    assert _exec_body(parse_vpy(str(p), syntax="jinja2"), N=1) == "big"
    assert _exec_body(parse_vpy(str(p), syntax="jinja2"), N=0) == ""


def test_if_else_with_bare_endif(tmp_path):
    src = textwrap.dedent("""\
        {% if N > 0: %}
        big
        {% else: %}
        zero
        {% endif %}
        """)
    p = _vpy(tmp_path, src)
    assert _exec_body(parse_vpy(str(p), syntax="jinja2"), N=1) == "big"
    assert _exec_body(parse_vpy(str(p), syntax="jinja2"), N=0) == "zero"


def test_while_with_bare_endwhile(tmp_path):
    src = textwrap.dedent("""\
        {% i = 0 %}
        {% while i < 3: %}
        x{{ i }}
        {%     i += 1 %}
        {% endwhile %}
        """)
    p = _vpy(tmp_path, src)
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    assert out == "x0\nx1\nx2"


def test_nested_loops_bare_keywords(tmp_path):
    src = textwrap.dedent("""\
        {% for i in range(2): %}
        {%     for j in range(2): %}
        c[{{ i }}][{{ j }}]
        {%     endfor %}
        {% endfor %}
        """)
    p = _vpy(tmp_path, src)
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    assert out == "c[0][0]\nc[0][1]\nc[1][0]\nc[1][1]"


def test_mixed_sentinel_and_bare(tmp_path):
    # Outer: bare; inner: sentinel.
    src1 = textwrap.dedent("""\
        {% for i in range(2): %}
        {%     for j in range(2): %}
        a[{{ i }}][{{ j }}]
        {%     # endfor %}
        {% endfor %}
        """)
    # Outer: sentinel; inner: bare.
    src2 = textwrap.dedent("""\
        {% for i in range(2): %}
        {%     for j in range(2): %}
        a[{{ i }}][{{ j }}]
        {%     endfor %}
        {% # endfor %}
        """)
    p1 = _vpy(tmp_path, src1)
    p2 = tmp_path / "t2.vpy"
    p2.write_text(src2)
    out1 = _exec_body(parse_vpy(str(p1), syntax="jinja2"))
    out2 = _exec_body(parse_vpy(str(p2), syntax="jinja2"))
    expected = "a[0][0]\na[0][1]\na[1][0]\na[1][1]"
    assert out1 == expected
    assert out2 == expected


def test_bare_endfor_without_opener_errors(tmp_path):
    src = "{% endfor %}\n"
    p = _vpy(tmp_path, src)
    with pytest.raises(ParseError, match="without matching opener"):
        parse_vpy(str(p), syntax="jinja2")


def test_bare_endif_without_opener_errors(tmp_path):
    src = "{% endif %}\n"
    p = _vpy(tmp_path, src)
    with pytest.raises(ParseError, match="without matching opener"):
        parse_vpy(str(p), syntax="jinja2")


def test_sentinel_endfor_without_opener_errors(tmp_path):
    # Sentinel-comment close form must error on unmatched-opener too,
    # symmetric with the bare-keyword form.
    src = "{% # endfor %}\n"
    p = _vpy(tmp_path, src)
    with pytest.raises(ParseError, match="without matching opener"):
        parse_vpy(str(p), syntax="jinja2")


def test_double_close_sentinel_then_bare_errors(tmp_path):
    # `{% # endfor %}` already closes the for-block; the trailing bare
    # `{% endfor %}` is then unmatched and must error.
    src = textwrap.dedent("""\
        {% for i in range(2): %}
        hello
        {% # endfor %}
        between
        {% endfor %}
        """)
    p = _vpy(tmp_path, src)
    with pytest.raises(ParseError, match="without matching opener"):
        parse_vpy(str(p), syntax="jinja2")


def test_genesis_directive_passes_through_in_jinja2_mode(tmp_path):
    # `//;` is the genesis-mode directive sentinel; in jinja2 mode it has
    # no special meaning and must round-trip as plain Verilog text. Guards
    # against a regression where the parser silently recognises both
    # delimiter sets.
    src = textwrap.dedent("""\
        //; for i in range(3):
        wire foo;
        //; # endfor
        """)
    p = _vpy(tmp_path, src)
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    # Each input line emerges verbatim — no loop unroll, no directive
    # consumption.
    assert out == "//; for i in range(3):\nwire foo;\n//; # endfor"


def test_endfor_substring_not_keyword(tmp_path):
    # `endfor_x = 1` is regular Python, not a block close: the parser
    # must NOT pop the for-block when it encounters this directive.
    src = textwrap.dedent("""\
        {% for i in range(2): %}
        {%     endfor_x = i %}
        x{{ i }}
        {% endfor %}
        """)
    p = _vpy(tmp_path, src)
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    assert out == "x0\nx1"


def test_bare_endfor_with_whitespace_modifiers(tmp_path):
    # `{%- endfor -%}` is the whitespace-modified form; modifiers are a
    # syntactic no-op but must not block keyword recognition.
    src = textwrap.dedent("""\
        {% for i in range(2): %}
        y{{ i }}
        {%- endfor -%}
        """)
    p = _vpy(tmp_path, src)
    out = _exec_body(parse_vpy(str(p), syntax="jinja2"))
    assert out == "y0\ny1"


def test_roundtrip_equivalence(tmp_path):
    genesis_src = textwrap.dedent("""\
        //; W = 8
        //; for i in range(W):
        wire [`W-1`:0] r`i`;
        //; # endfor
        """)
    jinja2_src = textwrap.dedent("""\
        {% W = 8 %}
        {% for i in range(W): %}
        wire [{{ W-1 }}:0] r{{ i }};
        {% # endfor %}
        """)
    pg = tmp_path / "g.vpy"
    pg.write_text(genesis_src)
    pj = tmp_path / "j.vpy"
    pj.write_text(jinja2_src)
    out_g = _exec_body(parse_vpy(str(pg)))
    out_j = _exec_body(parse_vpy(str(pj), syntax="jinja2"))
    assert out_g == out_j
