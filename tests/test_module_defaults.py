"""--defaults: per-module parameter defaults from a BLOCK_PARAMS tree, the lowest config tier."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from genesispy.cli import parse_args
from genesispy.manager import Manager

LEAF = (
    "//; N = parameter('N', 1)\n"
    "//; M = parameter('M', 2)\n"
    "module `mname` (input clk);\n"
    "// N=`N` M=`M`\n"
    "endmodule\n"
)


def _top(inst: str = "//; u = unique_inst('leaf', 'u')\n") -> str:
    return inst + "module `mname` (input clk);\n`u.instantiate()` (.clk(clk));\nendmodule\n"


def _write_defaults(tmp_path: Path, tree: dict, name: str = "d.py") -> str:
    path = tmp_path / name
    if name.endswith(".json"):
        path.write_text(json.dumps(tree))
    else:
        path.write_text(f"BLOCK_PARAMS = {tree!r}\n")
    return name


def _design(tmp_path: Path, top: str | None = None, leaf: str = LEAF) -> list[str]:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "leaf.vpy").write_text(leaf)
    (tmp_path / "src" / "top.vpy").write_text(_top() if top is None else top)
    return ["--input", "top.vpy", "--input", "leaf.vpy", "--top", "top", "--src-path", "src",
            "--out-dir", "out"]


def _run(tmp_path: Path, argv: list[str], monkeypatch) -> int:
    monkeypatch.chdir(tmp_path)
    return Manager(parse_args(argv)).execute()


def _leaf_text(tmp_path: Path, name: str = "leaf") -> str:
    files = sorted((tmp_path / "out").glob(f"{name}*.v"))
    assert files, sorted(p.name for p in (tmp_path / "out").iterdir())
    return files[0].read_text()


@pytest.mark.parametrize("fname", ["d.py", "d.json"])
def test_entry_value_replaces_the_declared_default(tmp_path, monkeypatch, fname):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"leaf": {"N": 5}}, fname)
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert "// N=5 M=2" in _leaf_text(tmp_path)


def test_python_values_keep_their_type(tmp_path, monkeypatch):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"leaf": {"N": [3, 4], "M": "fast"}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert "// N=[3, 4] M=fast" in _leaf_text(tmp_path)


def test_no_entry_keeps_the_declared_default(tmp_path, monkeypatch):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"leaf": {"M": 7}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert "// N=1 M=7" in _leaf_text(tmp_path)


FORCED_LEAF = LEAF.replace("parameter('N', 1)", "parameter('N', 9, force=True)")
JSON_CFG = {"HierarchyTop": {"InstanceName": "top", "SubInstances": [
    {"InstanceName": "u", "Parameters": [{"Name": "N", "__Val__": 9}]}]}}


@pytest.mark.parametrize("source", ["cfg", "json", "p_bare", "p_scoped", "parent", "force"])
def test_every_other_source_outranks_a_default(tmp_path, monkeypatch, source):
    top = _top("//; u = unique_inst('leaf', 'u', N=9)\n") if source == "parent" else None
    argv = _design(tmp_path, top, FORCED_LEAF if source == "force" else LEAF)
    extra = {
        "cfg": ["--cfg", "w.cfg"],
        "json": ["--json-cfg", "c.json"],
        "p_bare": ["-p", "N=9", "--params-global"],
        "p_scoped": ["-p", "top.u.N=9"],
    }.get(source, [])
    (tmp_path / "w.cfg").write_text("configure('top.u.N', 9)\n")
    (tmp_path / "c.json").write_text(json.dumps(JSON_CFG))
    d = _write_defaults(tmp_path, {"leaf": {"N": 5}})
    assert _run(tmp_path, [*argv, *extra, "--defaults", d], monkeypatch) == 0
    assert "// N=9 M=2" in _leaf_text(tmp_path)


def test_generated_name_falls_back_to_the_template_entry_per_key(tmp_path, monkeypatch):
    argv = _design(tmp_path, _top("//; u = generate_w_name('leaf', 'leaf_fast', 'u')\n"))
    d = _write_defaults(tmp_path, {"leaf": {"N": 5, "M": 6}, "leaf_fast": {"N": 8}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert "// N=8 M=6" in _leaf_text(tmp_path, "leaf_fast")


def test_nested_entry_is_found_and_dict_values_are_not_parameters(tmp_path, monkeypatch):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"top": {"leaf": {"N": 5, "sub": {"M": 3}}}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    # sub is a child entry of leaf, not leaf's M
    assert "// N=5 M=2" in _leaf_text(tmp_path)


def test_several_files_combine(tmp_path, monkeypatch):
    argv = _design(tmp_path)
    a = _write_defaults(tmp_path, {"leaf": {"N": 5}}, "a.py")
    b = _write_defaults(tmp_path, {"top": {}}, "b.json")
    assert _run(tmp_path, [*argv, "--defaults", a, "--defaults", b], monkeypatch) == 0
    assert "// N=5 M=2" in _leaf_text(tmp_path)


@pytest.mark.parametrize(
    "files, message",
    [
        ({"d.py": {"grp": {"leaf": {"N": 5}}, "leaf": {"N": 6}}}, "leaf at grp.leaf and leaf"),
        ({"d.py": {"leaf": 5}}, "entry 'leaf' is not a dict"),
        ({"a.py": {"leaf": {"N": 5}}, "b.json": {"leaf": {"N": 6}}}, "leaf at"),
        ({"d.txt": {"leaf": {"N": 5}}}, "not a .py or .json file"),
    ],
)
def test_a_bad_tree_is_a_config_error(tmp_path, monkeypatch, capsys, files, message):
    argv = _design(tmp_path)
    for name, tree in files.items():
        (tmp_path / name).write_text(json.dumps(tree) if not name.endswith(".py")
                                     else f"BLOCK_PARAMS = {tree!r}\n")
    flags = [x for name in files for x in ("--defaults", name)]
    assert _run(tmp_path, [*argv, *flags], monkeypatch) != 0
    assert message in capsys.readouterr().err


def test_a_python_file_without_block_params_is_a_config_error(tmp_path, monkeypatch, capsys):
    argv = _design(tmp_path)
    (tmp_path / "d.py").write_text("PARAMS = {}\n")
    assert _run(tmp_path, [*argv, "--defaults", "d.py"], monkeypatch) != 0
    assert "no BLOCK_PARAMS dict" in capsys.readouterr().err


def test_a_missing_file_is_a_config_error(tmp_path, monkeypatch, capsys):
    argv = _design(tmp_path)
    assert _run(tmp_path, [*argv, "--defaults", "nope.py"], monkeypatch) != 0
    assert "nope.py" in capsys.readouterr().err


def test_unused_entries_and_keys_warn_but_pass(tmp_path, monkeypatch, capsys):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"leaf": {"N": 5, "TYPO": 1}, "ghost": {"N": 1}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    err = capsys.readouterr().err
    assert "default leaf.TYPO was never used (--defaults d.py)" in err
    assert "default ghost was never used (--defaults d.py)" in err
    assert "default leaf was never used" not in err


def test_param_footer_names_the_defaults_tier(tmp_path, monkeypatch):
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, {"leaf": {"N": 5}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert re.search(r"^//\s+N\s+: 5\s+<- defaults file \(--defaults\)$",
                     _leaf_text(tmp_path), re.M)


def test_identical_instances_still_share_one_module(tmp_path, monkeypatch):
    top = (
        "//; u = unique_inst('leaf', 'u')\n"
        "//; v = unique_inst('leaf', 'v')\n"
        "module `mname` (input clk);\n`u.instantiate()` (.clk(clk));\n"
        "`v.instantiate()` (.clk(clk));\nendmodule\n"
    )
    argv = _design(tmp_path, top)
    d = _write_defaults(tmp_path, {"leaf": {"N": 5}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert len(list((tmp_path / "out").glob("leaf*.v"))) == 1


# A key another tier outranks still counts as used; only a key nothing reads warns.
@pytest.mark.parametrize("extra, top", [
    ([], _top("//; u = unique_inst('leaf', 'u', N=9)\n")),
    (["-p", "N=9", "--params-global"], None),
    (["-p", "top.u.N=9"], None),
])
def test_an_outranked_key_counts_as_used(tmp_path, monkeypatch, capsys, extra, top):
    argv = _design(tmp_path, top)
    d = _write_defaults(tmp_path, {"leaf": {"N": 5}})
    assert _run(tmp_path, [*argv, *extra, "--defaults", d], monkeypatch) == 0
    assert "// N=9 M=2" in _leaf_text(tmp_path)
    assert "never used" not in capsys.readouterr().err


def test_a_key_behind_the_generated_name_entry_counts_as_used(tmp_path, monkeypatch, capsys):
    argv = _design(tmp_path, _top("//; u = generate_w_name('leaf', 'leaf_fast', 'u')\n"))
    d = _write_defaults(tmp_path, {"leaf": {"N": 5, "M": 6}, "leaf_fast": {"N": 8}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    assert "never used" not in capsys.readouterr().err


def test_a_key_for_a_forced_parameter_is_reported_forced(tmp_path, monkeypatch, capsys):
    argv = _design(tmp_path, leaf=FORCED_LEAF)
    d = _write_defaults(tmp_path, {"leaf": {"N": 5}})
    assert _run(tmp_path, [*argv, "--defaults", d], monkeypatch) == 0
    err = capsys.readouterr().err
    assert "default leaf.N is forced (--defaults d.py)" in err
    assert "never used" not in err


UNUSED_KINDS = {
    "overrides": ({"leaf": {"N": 5}}, ["-p", "top.v.N=1"],
                  "override top.v.N was never used"),
    "entries": ({"leaf": {"N": 5}, "ghost": {"N": 1}}, [], "default ghost was never used"),
    "keys": ({"leaf": {"N": 5, "TYPO": 1}}, [], "default leaf.TYPO was never used"),
}


@pytest.mark.parametrize("kind", sorted(UNUSED_KINDS))
def test_an_unused_kind_warns_without_strict(tmp_path, monkeypatch, capsys, kind):
    tree, extra, message = UNUSED_KINDS[kind]
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, tree)
    assert _run(tmp_path, [*argv, *extra, "--defaults", d], monkeypatch) == 0
    assert message in capsys.readouterr().err


@pytest.mark.parametrize("strict", ["{kind}", "all", "overrides,entries,keys"])
@pytest.mark.parametrize("kind", sorted(UNUSED_KINDS))
def test_a_strict_kind_fails_before_output(tmp_path, monkeypatch, capsys, kind, strict):
    tree, extra, message = UNUSED_KINDS[kind]
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, tree)
    flags = ["--strict-unused", strict.format(kind=kind)]
    assert _run(tmp_path, [*argv, *extra, "--defaults", d, *flags], monkeypatch) == 3
    err = capsys.readouterr().err
    assert re.search(rf"error:\S* {re.escape(message)}", err), err
    assert not list(tmp_path.glob("out/*.v"))


def test_an_unlisted_kind_stays_a_warning(tmp_path, monkeypatch, capsys):
    tree, extra, message = UNUSED_KINDS["entries"]
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, tree)
    assert _run(tmp_path, [*argv, "--defaults", d, "--strict-unused", "keys"], monkeypatch) == 0
    assert re.search(rf"warning:\S* {re.escape(message)}", capsys.readouterr().err)


def test_an_unknown_strict_kind_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        parse_args(["--strict-unused", "keys,bogus"])
    assert exc.value.code == 2


def test_ignore_unused_parses_like_strict_unused():
    assert parse_args([]).ignore_unused == frozenset()
    args = parse_args(["--ignore-unused", "entries", "--ignore-unused", "keys,"])
    assert args.ignore_unused == frozenset({"entries", "keys"})
    assert parse_args(["--ignore-unused", "all"]).ignore_unused == frozenset(
        {"overrides", "entries", "keys"})


def test_an_unknown_ignore_kind_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        parse_args(["--ignore-unused", "entry"])
    assert exc.value.code == 2
    assert "--ignore-unused: unknown kind 'entry'" in capsys.readouterr().err


def _run_kind(tmp_path: Path, monkeypatch, kind: str, flags: list[str]) -> tuple[int, str]:
    """Run the UNUSED_KINDS[kind] case with ``flags``; exit status and message."""
    tree, extra, message = UNUSED_KINDS[kind]
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, tree)
    return _run(tmp_path, [*argv, *extra, "--defaults", d, *flags], monkeypatch), message


def _reported(level: str, message: str, err: str) -> bool:
    return re.search(rf"{level}:\S* {re.escape(message)}", err) is not None


def test_an_ignored_kind_writes_nothing(tmp_path, monkeypatch, capsys):
    flags = ["--strict-unused", "keys", "--ignore-unused", "entries", "--log", "gen.log"]
    rc, message = _run_kind(tmp_path, monkeypatch, "entries", flags)
    assert rc == 0
    assert message not in capsys.readouterr().err
    assert not (tmp_path / "gen.log").exists()


def test_without_ignore_the_kind_still_warns_and_logs(tmp_path, monkeypatch, capsys):
    flags = ["--strict-unused", "keys", "--log", "gen.log"]
    rc, message = _run_kind(tmp_path, monkeypatch, "entries", flags)
    assert rc == 0
    assert _reported("warning", message, capsys.readouterr().err)
    assert message in (tmp_path / "gen.log").read_text()


def test_ignore_leaves_a_strict_kind_an_error(tmp_path, monkeypatch, capsys):
    flags = ["--ignore-unused", "entries", "--strict-unused", "keys"]
    rc, message = _run_kind(tmp_path, monkeypatch, "keys", flags)
    assert rc == 3
    assert _reported("error", message, capsys.readouterr().err)
    assert not list(tmp_path.glob("out/*.v"))


def test_ignore_leaves_an_unlisted_kind_a_warning(tmp_path, monkeypatch, capsys):
    rc, message = _run_kind(tmp_path, monkeypatch, "overrides", ["--ignore-unused", "entries"])
    assert rc == 0
    assert _reported("warning", message, capsys.readouterr().err)


def test_strict_wins_over_ignore(tmp_path, monkeypatch, capsys):
    flags = ["--ignore-unused", "entries", "--strict-unused", "entries"]
    rc, message = _run_kind(tmp_path, monkeypatch, "entries", flags)
    assert rc == 3
    assert _reported("error", message, capsys.readouterr().err)


@pytest.mark.parametrize("kind, status", [("entries", 0), ("overrides", 0), ("keys", 3)])
def test_ignore_all_with_one_strict_kind(tmp_path, monkeypatch, capsys, kind, status):
    flags = ["--ignore-unused", "all", "--strict-unused", "keys"]
    rc, message = _run_kind(tmp_path, monkeypatch, kind, flags)
    assert rc == status
    err = capsys.readouterr().err
    if status == 0:
        assert "never used" not in err
    else:
        assert _reported("error", message, err)


def test_strict_all_with_an_ignored_kind(tmp_path, monkeypatch, capsys):
    flags = ["--strict-unused", "all", "--ignore-unused", "entries"]
    rc, message = _run_kind(tmp_path, monkeypatch, "entries", flags)
    assert rc == 3
    assert _reported("error", message, capsys.readouterr().err)


def test_strict_all_and_ignore_all(tmp_path, monkeypatch, capsys):
    flags = ["--strict-unused", "all", "--ignore-unused", "all"]
    rc, message = _run_kind(tmp_path, monkeypatch, "keys", flags)
    assert rc == 3
    assert _reported("error", message, capsys.readouterr().err)


def test_an_ignored_kind_stays_out_of_a_written_log(tmp_path, monkeypatch):
    tree, _, entry_message = UNUSED_KINDS["entries"]
    _, extra, override_message = UNUSED_KINDS["overrides"]
    argv = _design(tmp_path)
    d = _write_defaults(tmp_path, tree)
    flags = ["--ignore-unused", "entries", "--log", "gen.log"]
    assert _run(tmp_path, [*argv, *extra, "--defaults", d, *flags], monkeypatch) == 0
    log = (tmp_path / "gen.log").read_text()
    assert override_message in log
    assert entry_message not in log


def _leaf_as_top(tmp_path: Path) -> list[str]:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "leaf.vpy").write_text(LEAF)
    return ["--input", "leaf.vpy", "--top", "leaf", "--src-path", "src", "--out-dir", "out"]


def test_defaults_entry_gives_the_top_a_named_entry(tmp_path, monkeypatch, capsys):
    argv = _leaf_as_top(tmp_path)
    d = _write_defaults(tmp_path, {"leaf_fast": {"N": 8}})
    flags = ["--defaults", d, "--defaults-entry", "leaf_fast"]
    assert _run(tmp_path, [*argv, *flags], monkeypatch) == 0
    assert "// N=8 M=2" in _leaf_text(tmp_path)
    assert "never used" not in capsys.readouterr().err


def test_defaults_entry_missing_from_every_file_is_an_error(tmp_path, monkeypatch, capsys):
    argv = _leaf_as_top(tmp_path)
    d = _write_defaults(tmp_path, {"leaf": {"N": 8}})
    flags = ["--defaults", d, "--defaults-entry", "ghost"]
    assert _run(tmp_path, [*argv, *flags], monkeypatch) == 1
    assert "--defaults-entry ghost" in capsys.readouterr().err


def test_defaults_entry_leaves_the_children_on_their_own_entries(tmp_path, monkeypatch):
    top = _top("//; T = parameter('T', 0)\n//; u = unique_inst('leaf', 'u')\n// T=`T`\n")
    argv = _design(tmp_path, top)
    d = _write_defaults(tmp_path, {"top_alt": {"T": 3, "N": 7}, "leaf": {"N": 5}})
    flags = ["--defaults", d, "--defaults-entry", "top_alt"]
    assert _run(tmp_path, [*argv, *flags], monkeypatch) == 0
    assert "// T=3" in _leaf_text(tmp_path, "top")
    assert "// N=5 M=2" in _leaf_text(tmp_path)
