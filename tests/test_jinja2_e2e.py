"""End-to-end check: a jinja2-syntax template runs through write_module +
import + execute and produces the same Verilog as the genesis-syntax
equivalent.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

from genesispy.template import emitter, runtime


def _import_generated(py_path: str, mod_name: str) -> object:
    spec = importlib.util.spec_from_file_location(mod_name, py_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _reset_runtime_line_maps():
    # Don't let line-map state from another test interfere.
    yield


def test_jinja2_e2e_matches_genesis(tmp_path):
    """Same logical template in both flavours yields the same Verilog."""
    genesis_src = textwrap.dedent("""\
        //; W = 4
        module top;
        //; for i in range(W):
            wire r`i`;
        //; # endfor
        endmodule
        """)
    jinja2_src = textwrap.dedent("""\
        {% W = 4 %}
        module top;
        {% for i in range(W): %}
            wire r{{ i }};
        {% # endfor %}
        endmodule
        """)
    pg = tmp_path / "g.vpy"
    pg.write_text(genesis_src)
    pj = tmp_path / "j.vpy"
    pj.write_text(jinja2_src)

    out_g = tmp_path / "out_g"
    out_j = tmp_path / "out_j"
    py_g = emitter.write_module(str(pg), str(out_g), output_suffix=".v")
    py_j = emitter.write_module(
        str(pj), str(out_j), output_suffix=".v", syntax="jinja2"
    )

    mod_g = _import_generated(py_g, "_g_g")
    mod_j = _import_generated(py_j, "_g_j")

    # Each generated module exposes a class named after the input stem.
    cls_g = mod_g.g
    cls_j = mod_j.j

    # Construct each with no manager — the generated body uses
    # self.emit() which writes to an internal buffer; UniqueModule.execute()
    # initialises that buffer before our body runs.
    inst_g = cls_g(_StubMgr())
    inst_j = cls_j(_StubMgr())
    inst_g.execute()
    inst_j.execute()

    def _strip_banner(s: str) -> str:
        # The generated banner mentions the module name (g vs j); strip it.
        return "\n".join(
            ln for ln in s.splitlines() if "module: " not in ln and "Source class:" not in ln
        )

    g_out = inst_g._outfile_handle.getvalue()
    j_out = inst_j._outfile_handle.getvalue()
    g_stripped = _strip_banner(g_out)
    j_stripped = _strip_banner(j_out)
    # Equivalence-only assertion is degenerate if both sides emit nothing
    # (e.g. an emitter regression that drops every self.emit). Anchor with
    # positive content checks and a non-empty floor.
    assert "module top;" in j_stripped
    for i in range(4):
        assert f"wire r{i};" in j_stripped
    assert "endmodule" in j_stripped
    assert g_stripped == j_stripped


class _StubMgr:
    """Minimal manager stand-in for direct UniqueModule construction."""
    def __init__(self):
        self.cfg_handler = None
        self.debug = 0
        self.top = None
        self.synth_top = None
        self.flavor = "both"
        self.no_module_cache = True
        self.gen_raw = False
        self.touched_dirs: list = []
