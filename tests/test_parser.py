"""Tests for genesispy.template.parser."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from genesispy.errors import ParseError
from genesispy.template.parser import parse_vpy


FIXTURES = Path(__file__).parent / "fixtures" / "parser"


def _normalise(text: str) -> str:
    """Normalise output for comparison: drop trailing whitespace per line and
    drop trailing blank lines."""
    return "\n".join(line.rstrip() for line in text.splitlines()).rstrip("\n")


def _load_expected(case: str, input_path: Path) -> str:
    """Load expected.py and substitute INPUT placeholder with the actual
    input file path."""
    raw = (FIXTURES / case / "expected.py").read_text()
    return raw.replace("INPUT", str(input_path))


@pytest.mark.parametrize(
    "case",
    [
        "plain_text",
        "python_line",
        "backtick_simple",
        "backtick_multiple",
        "loop",
        "nested_loop",
        "escape_quotes",
        "empty_lines",
        "include_directive",
    ],
)
def test_fixture_matches_expected(case: str) -> None:
    input_path = FIXTURES / case / "input.vpy"
    actual = parse_vpy(str(input_path))
    expected = _load_expected(case, input_path)
    assert _normalise(actual) == _normalise(expected), (
        f"Mismatch for {case}\n--- actual ---\n{actual}\n--- expected ---\n{expected}"
    )


@pytest.mark.parametrize(
    "case",
    [
        "plain_text",
        "python_line",
        "backtick_simple",
        "backtick_multiple",
        "loop",
        "nested_loop",
        "escape_quotes",
        "empty_lines",
        "include_directive",
    ],
)
def test_fixture_compiles(case: str) -> None:
    input_path = FIXTURES / case / "input.vpy"
    src = parse_vpy(str(input_path))
    # The emitted code is intended to live inside execute(), so it may use
    # 'self'.  Wrap it in a trivial function for compile().
    wrapped = "def _exec(self):\n" + "\n".join(
        ("    " + line if line.strip() else "") for line in src.splitlines()
    ) + "\n"
    compile(wrapped, str(input_path), "exec")


def test_legacy_vp_extension_rejected() -> None:
    bad = FIXTURES / "legacy_extension_rejected" / "input.vp"
    with pytest.raises(ParseError) as ei:
        parse_vpy(str(bad))
    assert ei.value.code == "parse_error"
    assert ".vp" in ei.value.msg


def test_legacy_svp_extension_rejected(tmp_path) -> None:
    p = tmp_path / "x.svp"
    p.write_text("module x; endmodule\n")
    with pytest.raises(ParseError) as ei:
        parse_vpy(str(p))
    assert ei.value.code == "parse_error"
    assert ".svp" in ei.value.msg


def test_custom_allowed_extension_parses(tmp_path) -> None:
    """An extension absent from the defaults parses cleanly when listed in ``allowed``."""
    p = tmp_path / "x.tvpy"
    p.write_text("module x; endmodule\n")
    out = parse_vpy(str(p), allowed=(".tvpy",))
    # Body is plain Verilog -> a single self.emit(...) call.
    assert "self.emit" in out


def test_unallowed_extension_rejected_with_expected_list(tmp_path) -> None:
    p = tmp_path / "x.tvpy"
    p.write_text("module x; endmodule\n")
    with pytest.raises(ParseError) as ei:
        parse_vpy(str(p), allowed=(".vpy", ".svpy"))
    assert ".tvpy" in ei.value.msg
    assert ".vpy" in ei.value.msg or ".svpy" in ei.value.msg


def test_tab_in_python_line_indent_rejected(tmp_path) -> None:
    p = tmp_path / "x.vpy"
    p.write_text("//;\tfor i in range(2):\n//; # endfor\n")
    with pytest.raises(ParseError) as ei:
        parse_vpy(str(p))
    assert ei.value.code == "parse_error"
    assert "tab character in //; indent" in ei.value.msg


def test_tab_after_spaces_in_python_line_indent_rejected(tmp_path) -> None:
    p = tmp_path / "x.vpy"
    # spaces then tab in the post-//; indent
    p.write_text("//;    \tfor i in range(2):\n//; # endfor\n")
    with pytest.raises(ParseError) as ei:
        parse_vpy(str(p))
    assert ei.value.code == "parse_error"
    assert "tab character in //; indent" in ei.value.msg


def test_custom_comment_directive_recognised(tmp_path) -> None:
    """``parse_vpy(..., comment="#")`` recognises ``#;`` as the directive."""
    p = tmp_path / "x.vpy"
    p.write_text("#; x = 1\nplain text\n")
    out = parse_vpy(str(p), comment="#")
    # The directive should have been consumed as a Python statement,
    # leaving 'x = 1' at column zero (not as emitted text).
    assert "x = 1" in out
    assert "self.emit(\"#; x = 1\")" not in out
    # Plain text is still emitted.
    assert 'self.emit("plain text")' in out


def test_custom_comment_directive_does_not_match_default(tmp_path) -> None:
    """With ``comment="#"``, ``//;`` lines are plain text, not directives."""
    p = tmp_path / "x.vpy"
    p.write_text("//; x = 1\n")
    out = parse_vpy(str(p), comment="#")
    # The //; line is now passed through as text via self.emit.
    assert "self.emit" in out
    assert "//;" in out


def test_misaligned_indent_rejected(tmp_path) -> None:
    # 3-space indent must raise; silent floor-to-0 would swallow scope.
    p = tmp_path / "x.vpy"
    p.write_text("//; if cond:\n//;   pass\n//; # endif\n")
    with pytest.raises(ParseError) as ei:
        parse_vpy(str(p))
    assert ei.value.code == "parse_error"
    assert "misaligned //; indent" in ei.value.msg


class _StubSelf:
    """Minimal stub bound to ``self`` when exec'ing parser output."""

    def __init__(self, params=None) -> None:
        self.lines: list[str] = []
        self._params = params or {}

    def emit(self, line: str) -> None:
        self.lines.append(line)

    def get_param(self, name: str):
        return self._params[name]

    def include(self, path: str) -> None:
        # No-op for testing.
        self.lines.append(f"<included {path}>")


def _exec_emitted(src: str, stub: _StubSelf) -> None:
    code = compile(src, "<emitted>", "exec")
    exec(code, {"self": stub})


_LOOP_EXPECTED = [
    line
    for i in range(3)
    for line in (f"  assign x[{i}] = 0;", f"  assign y[{i}] = 1;")
]
_NESTED_LOOP_EXPECTED = [
    f"  assign m[{i}][{j}] = 0;" for i in range(2) for j in range(2)
]


@pytest.mark.parametrize(
    "case,expected",
    [
        ("plain_text",      ["module foo;", "  wire x;", "endmodule"]),
        ("loop",            _LOOP_EXPECTED),
        ("nested_loop",     _NESTED_LOOP_EXPECTED),
        ("backtick_simple", ["wire [7:0] x;"]),
        ("escape_quotes",   ['$display("hello \\"world\\"");']),
        ("empty_lines",     ["module a;", "", "  wire x;", "", "endmodule"]),
    ],
)
def test_roundtrip(case: str, expected: list) -> None:
    src = parse_vpy(str(FIXTURES / case / "input.vpy"))
    stub = _StubSelf()
    _exec_emitted(src, stub)
    assert stub.lines == expected


def test_unterminated_backtick_raises(tmp_path) -> None:
    p = tmp_path / "bad.vpy"
    p.write_text("wire [`W-1:0] x;\n")
    with pytest.raises(ParseError) as ei:
        parse_vpy(str(p))
    assert ei.value.code == "parse_error"
    assert "backtick" in ei.value.msg


def test_get_param_example(tmp_path) -> None:
    """End-to-end example from the parser docstring."""
    p = tmp_path / "foo.vpy"
    p.write_text(
        "module foo (\n"
        '//; w = self.get_param("WIDTH")\n'
        "  input  [`w-1`:0] in,\n"
        "  output [`w-1`:0] out\n"
        ");\n"
        "//; for i in range(w):\n"
        "  assign out[`i`] = ~in[`i`];\n"
        "//; # endfor\n"
        "endmodule\n"
    )
    src = parse_vpy(str(p))
    stub = _StubSelf(params={"WIDTH": 4})
    _exec_emitted(src, stub)
    assert stub.lines == [
        "module foo (",
        "  input  [3:0] in,",
        "  output [3:0] out",
        ");",
        "  assign out[0] = ~in[0];",
        "  assign out[1] = ~in[1];",
        "  assign out[2] = ~in[2];",
        "  assign out[3] = ~in[3];",
        "endmodule",
    ]


def test_line_directives_present() -> None:
    src = parse_vpy(str(FIXTURES / "plain_text" / "input.vpy"))
    # Should have a # line N "FILE" directive for each input line.
    for n in (1, 2, 3):
        assert f'# line {n} "' in src


def test_line_directives_escape_quotes_in_path(tmp_path) -> None:
    """Bug #6: path containing `"` must round-trip through emit + parse."""
    from genesispy.template.runtime import _LINE_DIRECTIVE, build_line_map

    src_dir = tmp_path / 'q"q'
    src_dir.mkdir()
    p = src_dir / "in.vpy"
    p.write_text("module foo;\nendmodule\n")

    src = parse_vpy(str(p))
    line_map = build_line_map(src)
    assert line_map, "no line directives matched after path-escaping"
    files = {f for f, _ in line_map.values()}
    assert str(p) in files, f"escaped path missing from line map: {files!r}"

    import json as _json
    matched = False
    for line in src.splitlines():
        m = _LINE_DIRECTIVE.fullmatch(line)
        if m:
            decoded = _json.loads(m.group(2))
            assert decoded == str(p)
            matched = True
            break
    assert matched, "no line directive matched the regex"
