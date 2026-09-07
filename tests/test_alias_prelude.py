"""Tests for the canonical bare-name alias table.

These guard against regressions where the three alias-prelude call sites
(template/emitter.py, user_config._include, gvpy_cli._build_class_from_vpy)
drift apart again.
"""

from __future__ import annotations

import re

import ast
from types import SimpleNamespace

import pytest

from genesispy.template.aliases import (
    EXPECTED_ALIAS_KEYS as EXPECTED_KEYS,
    SIMPLE_ALIASES,
    alias_dict,
    alias_prelude_source,
)


def _fake_self():
    target_attrs = {attr for _, attr in SIMPLE_ALIASES}
    ns = SimpleNamespace(**{a: f"<{a}>" for a in target_attrs})
    # The four shortname-source attributes that alias_dict reads.
    ns._unique_module_name = "Foo_unq0"
    ns._instance_name = "u_foo"
    ns._module_name = "Foo"
    return ns


def test_alias_dict_keys_match_expected():
    d = alias_dict(_fake_self())
    assert set(d) == EXPECTED_KEYS


def test_alias_dict_binds_pyinclude_to_given_namespace(tmp_path, monkeypatch):
    """Both include spellings populate the ``ns`` handed to alias_dict."""
    py = tmp_path / "snippet.py"
    py.write_text("VALUE = 41\n")

    ns: dict = {}
    d = alias_dict(_fake_self(), ns)
    ns.update(d)

    monkeypatch.chdir(tmp_path)
    d["pyinclude"]("snippet.py")
    assert ns["VALUE"] == 41

    ns["VALUE"] = 0
    d["pinclude"]("snippet.py")
    assert ns["VALUE"] == 41


def test_alias_dict_without_namespace_raises_on_call():
    d = alias_dict(_fake_self())
    for name in ("pyinclude", "pinclude"):
        with pytest.raises(RuntimeError, match="without a namespace"):
            d[name]("anything.py")


def test_alias_dict_include_resolves_to_user_config_include():
    from genesispy import user_config

    d = alias_dict(_fake_self())
    assert d["include"] is user_config._include


def test_alias_prelude_source_parses_as_python():
    src = "def execute(self):\n" + alias_prelude_source(indent="    ")
    src += "    pass\n"
    ast.parse(src)


def test_alias_prelude_source_uses_caller_indent():
    src = alias_prelude_source(indent="        ")
    for line in src.splitlines():
        if line.strip():
            assert line.startswith("        "), line


def test_alias_prelude_source_binds_all_expected_names():
    src = alias_prelude_source(indent="")
    bound = set()
    for line in src.splitlines():
        m = re.match(r"\s*(?:def\s+(\w+)\s*\(|(\w+)\s*=)", line)
        if m:
            bound.add(m.group(1) or m.group(2))
    assert set(EXPECTED_KEYS) <= bound, set(EXPECTED_KEYS) - bound


def _norm_alias_lines(src: str) -> set[tuple[str, str]]:
    out = set()
    for ln in src.splitlines():
        if "=" in ln and ln.strip():
            lhs, _, rhs = ln.partition("=")
            out.add((lhs.strip(), rhs.strip()))
    return out


def test_emitter_header_binds_every_table_alias():
    """`_header()` must bind every name in the alias table to its target."""
    from genesispy.template.emitter import _header

    src = _header("x.vpy", "X", ".v")
    actual = _norm_alias_lines(src)
    for name, attr in SIMPLE_ALIASES:
        if name == "synonym":
            # Arity dispatcher: a def, not an assignment.
            assert "def synonym(*_args):" in src
            continue
        assert (name, f"self.{attr}") in actual, (name, attr)
    bound = {lhs for lhs, _ in actual}
    assert set(EXPECTED_KEYS) - {"synonym", "include", "pyinclude", "pinclude"} <= bound


def test_include_namespace_includes_include_and_pyinclude(tmp_path, monkeypatch):
    """Included `.vpy` files can call bare `include`/`pyinclude`/`pinclude`."""
    from genesispy import user_config

    inner = tmp_path / "inner.vpy"
    # No actual include() call (would need a real Manager); just reference the
    # bare names so a NameError surfaces if either is missing from the
    # exec-globals dict.
    inner.write_text(
        "//;_ = include\n"
        "//;_ = pyinclude\n"
        "//;_ = pinclude\n"
    )

    from genesispy.template.aliases import SIMPLE_ALIASES

    class _StubMod:
        def __init__(self):
            for _, attr in SIMPLE_ALIASES:
                setattr(self, attr, lambda *a, **kw: None)

    class _StubMgr:
        inc_path: list[str] = []
        def find_file(self, path, search):
            return path

    monkeypatch.setattr(user_config, "_current_manager", lambda: _StubMgr())
    monkeypatch.setattr(user_config, "_current_module", lambda: _StubMod())

    user_config._include(str(inner))


def test_gvpy_class_factory_source_uses_canonical_prelude(monkeypatch, tmp_path):
    """`_build_class_from_vpy` must include every alias from the canonical table."""
    from genesispy import gvpy_cli

    captured = {}

    real_compile = compile

    def spy_compile(src, filename, mode, *a, **kw):
        captured["src"] = src
        return real_compile(src, filename, mode, *a, **kw)

    monkeypatch.setattr(gvpy_cli, "compile", spy_compile, raising=False)

    vpy = tmp_path / "stub.vpy"
    vpy.write_text("")  # empty body — class factory only assembles source.
    gvpy_cli._build_class_from_vpy("stub", str(vpy))

    actual = _norm_alias_lines(captured["src"])
    assert "def synonym(*_args):" in captured["src"]
    for name, attr in SIMPLE_ALIASES:
        if name != "synonym":
            assert (name, f"self.{attr}") in actual, (name, attr)
