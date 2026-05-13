"""Tests for genesispy.config_handler."""

from __future__ import annotations

import os

import pytest

from genesispy.config_handler import ConfigHandler, Priority, _parse_cmdln_param

from tests._stubs import args_namespace as _make_manager  # noqa: E402


def test_priority_ordering():
    # Matches Perl Genesis2: CFG < XML < CMDLN.
    # Numeric values: CFG=10, XML=20, CMDLN=30.
    assert int(Priority.EXTERNAL_CONFIG) == 10
    assert int(Priority.EXTERNAL_PARAM_FILE) == 20
    assert int(Priority.CMD_LINE) == 30
    assert (
        Priority.EXTERNAL_CONFIG
        < Priority.EXTERNAL_PARAM_FILE
        < Priority.CMD_LINE
    )


def test_parse_cmdln_param():
    assert _parse_cmdln_param("WIDTH=8") == (None, "WIDTH", 8)
    assert _parse_cmdln_param("PI=3.14") == (None, "PI", 3.14)
    assert _parse_cmdln_param("FLAG=true") == (None, "FLAG", True)
    assert _parse_cmdln_param("FLAG=False") == (None, "FLAG", False)
    assert _parse_cmdln_param("NAME=foo") == (None, "NAME", "foo")


def test_parse_cmdln_param_hierarchical():
    assert _parse_cmdln_param("top.child.x=2") == (("top", "child"), "x", 2)
    assert _parse_cmdln_param("a.b.c.d.x=hi") == (
        ("a", "b", "c", "d"),
        "x",
        "hi",
    )
    # Single-level path.
    assert _parse_cmdln_param("top.x=5") == (("top",), "x", 5)


def test_parse_cmdln_param_rejects_empty_segments():
    import pytest
    from genesispy.reporting import ParameterError

    with pytest.raises(ParameterError):
        _parse_cmdln_param(".x=1")
    with pytest.raises(ParameterError):
        _parse_cmdln_param("a..b.x=1")
    with pytest.raises(ParameterError):
        _parse_cmdln_param("a.=1")


def test_parse_cmdln_param_rejects_type_suffix():
    import pytest
    from genesispy.reporting import ParameterError

    # Perl ':TYPE=VAL' form is not ported; reject rather than silently strip.
    with pytest.raises(ParameterError) as ei:
        _parse_cmdln_param("X:=8")
    assert ei.value.code == "parameter_error"
    assert "TYPE" in ei.value.msg
    with pytest.raises(ParameterError) as ei:
        _parse_cmdln_param("X:int=8")
    assert ei.value.code == "parameter_error"
    assert "TYPE" in ei.value.msg


def test_cmdln_population_from_manager():
    m = _make_manager(parameter=["WIDTH=8", "DEBUG=true"])
    ch = ConfigHandler(m)
    assert ch.get_cmdln_param_val("WIDTH") == 8
    assert ch.get_cmdln_param_val("DEBUG") is True
    assert ch.get_cmdln_param_val("MISSING") is None


def test_configure_priority_aware_writes(capsys):
    """Lower-priority second configure is a no-op; equal-or-higher overwrites and warns."""
    ch = ConfigHandler(_make_manager())

    # Higher priority first; lower second must not overwrite, must not warn.
    ch.configure("X", 1, priority=Priority.EXTERNAL_CONFIG)
    capsys.readouterr()  # drain
    ch.configure("X", 99, priority=Priority.DECLARATION)
    assert ch.get_configuration("X") == 1
    assert "redefinition" not in capsys.readouterr().err

    # Equal-priority second overwrites and warns.
    ch.configure("X", 2, priority=Priority.EXTERNAL_CONFIG)
    assert ch.get_configuration("X") == 2
    assert "redefinition" in capsys.readouterr().err


def test_scoped_cfg_configure_via_dotted_name():
    """`configure("top.foo.X", v)` from .cfg reaches `parameter("X")` inside `top.foo`."""
    ch = ConfigHandler(_make_manager())
    ch.configure("top.child.WIDTH", 64)
    # Exact path match returns scoped value.
    assert ch.get_configuration(
        "WIDTH", instance_path=("top", "child")
    ) == 64
    # Different path: no match, falls through to flat (also empty).
    assert ch.get_configuration(
        "WIDTH", instance_path=("top", "other")
    ) is None
    # Flat configure unaffected.
    assert ch.get_configuration("WIDTH") is None
    # exists_configuration honours the scoped entry.
    assert ch.exists_configuration(
        "WIDTH", instance_path=("top", "child")
    )
    assert not ch.exists_configuration("WIDTH")


def test_scoped_cmdln_lookup_exact_match():
    m = _make_manager(parameter=["top.child2.out_val=2"])
    ch = ConfigHandler(m)
    # Exact path match returns scoped value.
    assert ch.get_configuration(
        "out_val", instance_path=("top", "child2")
    ) == 2
    # Different leaf -> no match.
    assert ch.get_configuration(
        "out_val", instance_path=("top", "child1")
    ) is None
    # Different parent -> no match.
    assert ch.get_configuration(
        "out_val", instance_path=("other", "child2")
    ) is None
    # No path argument -> scoped DB ignored.
    assert ch.get_configuration("out_val") is None
    # exists_configuration mirrors lookup.
    assert ch.exists_configuration(
        "out_val", instance_path=("top", "child2")
    )
    assert not ch.exists_configuration("out_val")


def test_scoped_cmdln_wins_over_flat_for_matching_path():
    m = _make_manager(
        parameter=["x=1", "top.a.x=99"]
    )
    ch = ConfigHandler(m)
    # Matching path: scoped wins.
    assert ch.get_configuration("x", instance_path=("top", "a")) == 99
    # Non-matching path: scoped doesn't apply, flat is used.
    assert ch.get_configuration("x", instance_path=("top", "b")) == 1
    # No path: flat only.
    assert ch.get_configuration("x") == 1


def test_duplicate_scoped_cmdln_raises():
    # Duplicate scoped --parameter raises ParameterError, not warn-and-keep-first.
    from genesispy.reporting import ParameterError

    m = _make_manager(parameter=["top.a.x=1", "top.a.x=2"])
    with pytest.raises(ParameterError) as ei:
        ConfigHandler(m)
    assert ei.value.code == "parameter_error"
    assert "Duplicate" in ei.value.msg


def test_duplicate_flat_cmdln_raises():
    from genesispy.reporting import ParameterError

    m = _make_manager(parameter=["WIDTH=8", "WIDTH=16"])
    with pytest.raises(ParameterError) as ei:
        ConfigHandler(m)
    assert ei.value.code == "parameter_error"
    assert "Duplicate" in ei.value.msg


def test_xml_explicit_null_distinguishable_from_absent(tmp_path):
    # Explicit null in JSON must not collapse with "not found" — exists_configuration
    # returns True for explicit null, False for absence (_MISSING sentinel).
    json_p = tmp_path / "cfg.json"
    json_p.write_text(
        '{"HierarchyTop": {"Parameters": ['
        '{"Name": "EXPLICIT_NULL", "__Val__": null}'
        "]}}"
    )
    ch = ConfigHandler(_make_manager())
    ch.read_json(str(json_p))

    # Explicit null: present, value None.
    assert ch.exists_configuration("EXPLICIT_NULL") is True
    assert ch.get_param_val("EXPLICIT_NULL") is None

    # Truly absent name: not present.
    assert ch.exists_configuration("NEVER_SET") is False


def test_get_param_val_malformed_parameter_returns_none(tmp_path):
    """A Parameter with no value-bearing key is treated as missing."""
    json_path = tmp_path / "c.json"
    json_path.write_text(
        '{"HierarchyTop": {"Parameters": [{"Name": "X"}]}}'
    )
    ch = ConfigHandler(_make_manager())
    ch.read_json(str(json_path))
    assert ch.get_param_val("X") is None


def test_input_immutable_parameters_ignored(tmp_path):
    """Matches Genesis2: input ``ImmutableParameters`` is writeback-only
    metadata. Values nested under it must not be picked up as overrides;
    only ``Parameters`` is a value source."""
    json_p = tmp_path / "cfg.json"
    json_p.write_text(
        '{"HierarchyTop": {"ImmutableParameters": ['
        '{"Name": "PINNED", "__Val__": 42}'
        "]}}"
    )
    ch = ConfigHandler(_make_manager())
    ch.read_json(str(json_p))
    assert ch.exists_configuration("PINNED") is False
    assert ch.get_param_val("PINNED") is None


def test_read_json_wraps_decode_error(tmp_path):
    """Bug #3: malformed JSON must raise ConfigError, not raw JSONDecodeError."""
    from genesispy.reporting import ConfigError

    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    ch = ConfigHandler(_make_manager())
    with pytest.raises(ConfigError) as ei:
        ch.read_json(str(p))
    assert ei.value.code == "config_error"
    assert "bad.json" in str(ei.value)


def test_json_overrides_cfg(tmp_path):
    json_path = tmp_path / "c.json"
    json_path.write_text(
        '{"HierarchyTop": {"Parameters": ['
        '{"Name": "WIDTH", "__Val__": 4}'
        "]}}"
    )
    cfg_path = tmp_path / "c.cfg"
    cfg_path.write_text("configure('WIDTH', 16)\n")

    ch = ConfigHandler(_make_manager())
    ch.read_json(str(json_path))
    assert ch.get_param_val("WIDTH") == 4
    ch.read_cfg(str(cfg_path))
    assert ch.get_cfg_param_val("WIDTH") == 16
    # JSON outranks .cfg (matches Perl Genesis2).
    assert ch.get_configuration("WIDTH") == 4


def test_cmdln_overrides_json_overrides_cfg(tmp_path):
    json_path = tmp_path / "c.json"
    json_path.write_text(
        '{"HierarchyTop": {"Parameters": ['
        '{"Name": "X", "__Val__": 1}'
        "]}}"
    )
    cfg_path = tmp_path / "c.cfg"
    cfg_path.write_text("configure('X', 2)\n")

    ch = ConfigHandler(_make_manager(parameter=["X=99"]))
    ch.read_json(str(json_path))
    ch.read_cfg(str(cfg_path))
    assert ch.get_configuration("X") == 99
    assert ch.get_param_val("X") == 1
    assert ch.get_cfg_param_val("X") == 2
    assert ch.get_cmdln_param_val("X") == 99

    # Without CLI: JSON wins over .cfg.
    ch2 = ConfigHandler(_make_manager())
    ch2.read_json(str(json_path))
    ch2.read_cfg(str(cfg_path))
    assert ch2.get_configuration("X") == 1


def test_simple_cfg_sandbox(tmp_path):
    cfg_path = tmp_path / "c.cfg"
    cfg_path.write_text(
        "configure('WIDTH', 8)\n"
        "configure('NAME', 'top')\n"
        "if exists_configuration('WIDTH'):\n"
        "    configure('DOUBLED', get_configuration('WIDTH') * 2)\n"
    )

    ch = ConfigHandler(_make_manager())
    ch.read_cfg(str(cfg_path))
    assert ch.get_configuration("WIDTH") == 8
    assert ch.get_configuration("NAME") == "top"
    assert ch.get_configuration("DOUBLED") == 16


def test_exists_and_remove(tmp_path):
    cfg_path = tmp_path / "c.cfg"
    cfg_path.write_text("configure('A', 1)\n")
    ch = ConfigHandler(_make_manager())
    ch.read_cfg(str(cfg_path))
    assert ch.exists_configuration("A")
    ch.remove_configuration("A")
    assert not ch.exists_configuration("A")
    assert ch.get_configuration("A") is None


def test_print_configuration_non_empty(tmp_path):
    cfg_path = tmp_path / "c.cfg"
    cfg_path.write_text("configure('WIDTH', 8)\n")

    ch = ConfigHandler(_make_manager(parameter=["DEBUG=true"]))
    ch.read_cfg(str(cfg_path))
    s = ch.print_configuration()
    assert isinstance(s, str)
    assert len(s) > 0
    assert "WIDTH" in s
    assert "DEBUG" in s


def test_configure_with_type_bool():
    ch = ConfigHandler(_make_manager())
    ch.configure("FLAG", "true", type="bool")
    assert ch.get_cfg_param_val("FLAG") is True
    ch.configure("FLAG2", "0", type="bool")
    assert ch.get_cfg_param_val("FLAG2") is False


def test_manager_does_not_re_ingest_parameter_overrides(tmp_path):
    # Manager._ensure_cfg_handler must not re-ingest --parameter (would
    # double-write to _cfg_db under bogus dotted names).
    from genesispy.cli import parse_args
    from genesispy.manager import Manager

    args = parse_args([
        "--input", "dummy.vpy",
        "--top", "dummy",
        "--parameter", "WIDTH=8",
        "--parameter", "top.foo.X=2",
    ])
    m = Manager(args)
    m._ensure_cfg_handler()
    ch = m.cfg_handler

    cmdln = ch.cmdln_db_snapshot()
    cfg = ch.cfg_db_snapshot()
    scoped = ch.cmdln_scoped_db_snapshot()

    # Flat override: in cmdln_db only, not cfg_db.
    assert "WIDTH" in cmdln
    assert "WIDTH" not in cfg

    # Scoped override: in cmdln_scoped_db only; the bogus flat key
    # "top.foo.X" must not appear in cfg_db.
    assert (("top", "foo"), "X") in scoped
    assert "top.foo.X" not in cfg
    assert "X" not in cfg
