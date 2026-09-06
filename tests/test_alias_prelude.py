"""Tests for the canonical bare-name alias table.

These guard against regressions where the three alias-prelude call sites
(template/emitter.py, user_config._include, gvpy_cli._build_class_from_vpy)
drift apart again.
"""

from __future__ import annotations

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
    for name in EXPECTED_KEYS:
        # Accept any binding form: `name = ...`, `name=...`, `name\t...`,
        # or `def name(...)` (used for the synonym arity dispatcher).
        assert (
            f"{name} " in src
            or f"{name}=" in src
            or f"{name}\t" in src
            or f"def {name}(" in src
        ), name


def _norm_alias_lines(src: str) -> set[tuple[str, str]]:
    out = set()
    for ln in src.splitlines():
        if "=" in ln and ln.strip():
            lhs, _, rhs = ln.partition("=")
            out.add((lhs.strip(), rhs.strip()))
    return out


def test_emitter_header_uses_canonical_prelude():
    """`_header()` must contain every binding from `alias_prelude_source`."""
    from genesispy.template.emitter import _header

    formatted = _header("x.vpy", "X", ".v")
    expected = _norm_alias_lines(alias_prelude_source(indent=""))
    actual = _norm_alias_lines(formatted)
    assert expected.issubset(actual), expected - actual


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

    src = captured["src"]
    expected = alias_prelude_source(indent="")
    for line in expected.splitlines():
        lhs = line.partition("=")[0].strip()
        if lhs:
            assert lhs in src, f"gvpy class factory missing alias: {lhs!r}"
