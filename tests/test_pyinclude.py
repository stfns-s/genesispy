"""pyinclude: raw-Python include into the calling code's own namespace."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from genesispy import cache, user_config
from genesispy.cli import parse_args
from genesispy.manager import Manager


HELPERS = (
    "import math\n"
    "\n"
    "TAPS_MAX = 64\n"
    "\n"
    "def taps(n):\n"
    "    return [1 << i for i in range(n)]\n"
    "\n"
    "def acc_width(weights, iw):\n"
    "    return iw + math.ceil(math.log2(sum(weights) + 1))\n"
)


@pytest.fixture(autouse=True)
def _reset_cache():
    cache.clear_all()
    yield
    cache.clear_all()


def _run(tmp_path: Path, argv: list[str]) -> Manager:
    """Run a Manager rooted at ``tmp_path``; assert a clean exit."""
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        m = Manager(parse_args(argv))
        assert m.execute() == 0
        return m
    finally:
        os.chdir(cwd)


def _run_failing(tmp_path: Path, argv: list[str]) -> int:
    """Run a Manager expected to fail; return its exit code.

    Manager.execute() catches elaboration errors and reports them through
    reporting.error, so the diagnostic lands on stderr rather than
    propagating -- assert on capsys, not pytest.raises.
    """
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return Manager(parse_args(argv)).execute()
    finally:
        os.chdir(cwd)


def _emitted(prefix: str) -> str:
    key = next(k for k in cache.OUTFILE_CONTENT_CACHE if k.startswith(prefix))
    return cache.OUTFILE_CONTENT_CACHE[key]


# ---------------------------------------------------------------------------
# 1. Definitions land in the module namespace and stay reachable
# ---------------------------------------------------------------------------
def test_pyincluded_names_reachable_as_bare_names(tmp_path: Path) -> None:
    """A def, an import and a constant from the .py all resolve later."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "helpers.py").write_text(HELPERS)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "dut.vpy").write_text(
        "//; pyinclude('helpers.py')\n"
        "//; w = taps(4)\n"
        "//; emit(f'// aw={acc_width(w, 8)} max={TAPS_MAX} n={math.isqrt(81)}')\n"
    )
    _run(tmp_path, [
        "--input", "src/dut.vpy", "--top", "dut",
        "--src-path", "src", "--py-path", "lib",
    ])
    # acc_width([1,2,4,8], 8) == 8 + ceil(log2(16)) == 12
    assert "// aw=12 max=64 n=9" in _emitted("dut")


# ---------------------------------------------------------------------------
# 2. Scoping: one module's pyinclude is invisible to another
# ---------------------------------------------------------------------------
def test_pyincluded_names_do_not_leak_to_another_module(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "helpers.py").write_text(HELPERS)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "leaf.vpy").write_text(
        "//; emit(f'// leaked={taps(2)}')\n"
    )
    (tmp_path / "src" / "dut.vpy").write_text(
        "//; pyinclude('helpers.py')\n"
        "//; unique_inst('leaf', 'u_leaf')\n"
    )
    rc = _run_failing(tmp_path, [
        "--input", "src/dut.vpy", "--top", "dut",
        "--src-path", "src", "--inc-path", "src", "--py-path", "lib",
    ])
    assert rc != 0
    err = capsys.readouterr().err
    assert "NameError" in err and "taps" in err, err


# ---------------------------------------------------------------------------
# 3. Resolution order: cwd, then --py-path, then --inc-path
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "layout, expected",
    [
        ({"lib": "py-path", "inc": "inc-path"}, "py-path"),
        ({"inc": "inc-path"}, "inc-path"),
        ({"lib": "py-path", "inc": "inc-path", ".": "cwd"}, "cwd"),
    ],
    ids=["py_path_wins_over_inc_path", "inc_path_alone", "cwd_wins"],
)
def test_resolution_order(tmp_path: Path, layout: dict, expected: str) -> None:
    for d in ("lib", "inc", "src"):
        (tmp_path / d).mkdir()
    for d, tag in layout.items():
        (tmp_path / d / "helpers.py").write_text(f"WHICH = {tag!r}\n")
    (tmp_path / "src" / "dut.vpy").write_text(
        "//; pyinclude('helpers.py')\n"
        "//; emit(f'// which={WHICH}')\n"
    )
    _run(tmp_path, [
        "--input", "src/dut.vpy", "--top", "dut",
        "--src-path", "src", "--py-path", "lib", "--inc-path", "inc",
    ])
    assert f"// which={expected}" in _emitted("dut")


# ---------------------------------------------------------------------------
# 4. Diagnostics
# ---------------------------------------------------------------------------
def test_missing_file_names_the_candidate_dirs(tmp_path: Path, capsys) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "dut.vpy").write_text("//; pyinclude('nope.py')\n")
    rc = _run_failing(tmp_path, [
        "--input", "src/dut.vpy", "--top", "dut",
        "--src-path", "src", "--py-path", "lib",
    ])
    assert rc != 0
    err = capsys.readouterr().err
    assert "nope.py" in err and "not found" in err and "lib" in err, err


def test_template_extension_is_rejected(tmp_path: Path, capsys) -> None:
    """pyinclude('x.vpy') names include(), not a SyntaxError."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "frag.vpy").write_text("//; emit('// frag')\n")
    (tmp_path / "src" / "dut.vpy").write_text("//; pyinclude('frag.vpy')\n")
    rc = _run_failing(tmp_path, [
        "--input", "src/dut.vpy", "--top", "dut",
        "--src-path", "src", "--inc-path", "src",
    ])
    assert rc != 0
    err = capsys.readouterr().err
    assert "is a template (.vpy); use include()" in err, err


# ---------------------------------------------------------------------------
# 5. .depend lists the .py exactly once across repeated instantiation
# ---------------------------------------------------------------------------
def test_depend_lists_the_python_file_once(tmp_path: Path) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "helpers.py").write_text(HELPERS)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "leaf.vpy").write_text(
        "//; pyinclude('helpers.py')\n"
        "//; N = parameter('N', 1)\n"
        "//; emit(f'// n={len(taps(N))}')\n"
    )
    (tmp_path / "src" / "dut.vpy").write_text(
        "//; for n in (1, 2, 3):\n"
        "//;     unique_inst('leaf', f'u{n}', N=n)\n"
        "//; # endfor\n"
    )
    _run(tmp_path, [
        "--input", "src/dut.vpy", "--top", "dut",
        "--src-path", "src", "--inc-path", "src", "--py-path", "lib",
    ])
    depend = (tmp_path / "genesis_synth" / "dut.depend").read_text()
    assert depend.count("helpers.py") == 2, depend  # prereq line + own target
    assert len(cache.INCLUDED_FILES) > 1, "re-exec'd per instantiation"


# ---------------------------------------------------------------------------
# 6. pinclude is a warn-once alias with identical behaviour
# ---------------------------------------------------------------------------
def test_pinclude_matches_pyinclude_and_warns_once(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "helpers.py").write_text(HELPERS)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "dut.vpy").write_text(
        "//; pinclude('helpers.py')\n"
        "//; pinclude('helpers.py')\n"
        "//; emit(f'// aw={acc_width(taps(4), 8)}')\n"
    )
    _run(tmp_path, [
        "--input", "src/dut.vpy", "--top", "dut",
        "--src-path", "src", "--py-path", "lib",
    ])
    assert "// aw=12" in _emitted("dut")
    err = capsys.readouterr().err
    assert err.count("pinclude is deprecated") == 1, err


# ---------------------------------------------------------------------------
# 7. Inside an include()'d snippet, the names are that snippet's
# ---------------------------------------------------------------------------
def test_pyinclude_inside_include_is_scoped_to_the_snippet(
    tmp_path: Path
) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "helpers.py").write_text(HELPERS)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "frag.vpy").write_text(
        "//; pyinclude('helpers.py')\n"
        "//; emit(f'// frag-sees={len(taps(3))}')\n"
    )
    (tmp_path / "src" / "dut.vpy").write_text(
        "//; include('frag.vpy')\n"
        "//; emit(f'// caller-sees={\"taps\" in dir()}')\n"
    )
    _run(tmp_path, [
        "--input", "src/dut.vpy", "--top", "dut",
        "--src-path", "src", "--inc-path", "src", "--py-path", "lib",
    ])
    text = _emitted("dut")
    assert "// frag-sees=3" in text
    assert "// caller-sees=False" in text


# ---------------------------------------------------------------------------
# Cache hygiene
# ---------------------------------------------------------------------------
def test_clear_all_resets_pyinclude_state(tmp_path: Path) -> None:
    py = tmp_path / "helpers.py"
    py.write_text("VALUE = 1\n")
    ns: dict = {}
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        user_config._make_pyinclude(ns)("helpers.py")
    finally:
        os.chdir(cwd)
    assert user_config._PYINCLUDE_CODE
    cache.clear_all()
    assert not user_config._PYINCLUDE_CODE
    assert user_config._PINCLUDE_WARNED is False
