"""Tests for genesispy.template.emitter."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from genesispy.template import emitter, runtime


def _write_vpy(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def test_emit_module_compiles(tmp_path: Path) -> None:
    body = 'self.emit("hello")\n'
    src = emitter.emit_module(str(tmp_path / "foo.vpy"), body)
    assert "class foo(UniqueModule, UserMixin):" in src
    assert "def execute(self):" in src
    assert "self.emit(\"hello\")" in src
    # Result must be valid Python.
    compile(src, "<emit_module>", "exec")


def test_emit_module_indents_body() -> None:
    body = 'for i in range(2):\n    self.emit(f"r{i}")\n'
    src = emitter.emit_module("/x/foo.vpy", body)
    # Each non-empty body line should now start with at least 8 spaces.
    body_lines = [
        ln for ln in src.splitlines()
        if ln.strip().startswith("for ") or ln.strip().startswith("self.emit(f\"r")
    ]
    assert body_lines, "expected to find indented body lines"
    for ln in body_lines:
        assert ln.startswith("        "), f"insufficient indent: {ln!r}"


def test_emit_module_empty_body_uses_pass() -> None:
    src = emitter.emit_module("/x/empty.vpy", "")
    assert "        pass" in src
    compile(src, "<emit_empty>", "exec")


def test_emit_module_custom_name() -> None:
    src = emitter.emit_module("/x/foo.vpy", "", module_name="MyMod")
    assert "class MyMod(UniqueModule, UserMixin):" in src


def test_emit_module_handles_braces_in_vpy_path() -> None:
    """A .vpy path containing literal {/} must not break the header."""
    weird = "/tmp/path{with}braces/foo.vpy"
    src = emitter.emit_module(weird, "")
    assert weird in src
    compile(src, "<emit_braces>", "exec")


def test_write_module_writes_file_and_registers_line_map(tmp_path: Path) -> None:
    vpy = _write_vpy(
        tmp_path,
        "alpha.vpy",
        "module alpha;\n//; w = 4\nendmodule\n",
    )
    out_dir = tmp_path / "raw"
    py_path = emitter.write_module(str(vpy), str(out_dir))

    assert os.path.isfile(py_path)
    assert py_path.endswith("alpha.py")
    text = Path(py_path).read_text()
    assert "class alpha(UniqueModule, UserMixin):" in text

    # Line map registered for this generated path.
    assert py_path in runtime.LINE_MAP
    mapping = runtime.LINE_MAP[py_path]
    assert mapping, "line map should not be empty"
    # All values point back at the .vpy.
    for src_path, src_lineno in mapping.values():
        assert src_path == str(vpy)
        assert isinstance(src_lineno, int)


def test_line_map_ignores_directive_inside_emit(tmp_path: Path) -> None:
    # Directive substring inside a self.emit() string must not match the regex.
    from genesispy.template import runtime as _rt
    src = '''self.emit("# line 99 \\"fake.vpy\\"")
self.emit("real")
'''
    mapping = _rt.build_line_map(src)
    # No directive in src -> no entries.
    assert mapping == {}


def test_remap_traceback_substitutes_vpy(tmp_path: Path) -> None:
    vpy = _write_vpy(tmp_path, "boom.vpy", "//; raise ValueError('x')\n")
    out_dir = tmp_path / "raw"
    py_path = emitter.write_module(str(vpy), str(out_dir))

    # Import the generated module and call execute -- expect ValueError.
    import importlib.util
    spec = importlib.util.spec_from_file_location("boom_gen", py_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class _StubMgr:
        cfg_handler = None
        output_suffix = ".v"
        no_module_cache = False

    inst = mod.boom(_StubMgr())  # type: ignore[arg-type]
    try:
        inst.execute()
    except ValueError as exc:
        formatted = runtime.remap_traceback(exc)
        assert "boom.vpy" in formatted
    else:
        pytest.fail("expected ValueError from generated module")


def test_emit_module_calls_param_footer_before_flush() -> None:
    """The generated tail emits the footer while the buffer is still open."""
    src = emitter.emit_module("x.vpy", "self.emit('hi')")
    assert "self.emit_param_footer()" in src
    assert src.index("self.emit_param_footer()") < src.index("self._flush_outfile()")
    compile(src, "x.py", "exec")


def test_class_body_tail_is_shared_with_the_footer() -> None:
    """gvpy reuses CLASS_BODY_TAIL; it must stay a prefix of _FOOTER."""
    assert emitter._FOOTER.startswith(emitter.CLASS_BODY_TAIL)
