"""Tests for the genesispy.tools.xml_json XML<->JSON helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from genesispy.tools import xml_json


_REPO_ROOT = Path(__file__).resolve().parents[1]
_BIN_DIR = _REPO_ROOT / "bin"


SAMPLE_XML = """\
<config>
  <Parameters>
    <Parameter>
      <Name>WIDTH</Name>
      <Val>8</Val>
    </Parameter>
    <Parameter>
      <Name>SIZES</Name>
      <ArrayType>
        <ArrayItem><Val>2</Val></ArrayItem>
        <ArrayItem><Val>5</Val></ArrayItem>
      </ArrayType>
    </Parameter>
    <Parameter>
      <Name>OPTS</Name>
      <HashType>
        <HashItem><Key>a</Key><Val>1</Val></HashItem>
        <HashItem><Key>b</Key><Val>2</Val></HashItem>
      </HashType>
    </Parameter>
  </Parameters>
</config>
"""


def test_xml_to_json_scalar_typing(tmp_path):
    src = tmp_path / "in.xml"
    src.write_text(SAMPLE_XML)
    dst = tmp_path / "out.json"

    xml_json.xml_to_json(str(src), str(dst))

    data = json.loads(dst.read_text())
    params = data["config"]["Parameters"]
    by_name = {p["Name"]: p for p in params}
    # Scalars are typed (XML "8" -> int 8).
    assert by_name["WIDTH"]["__Val__"] == 8
    # Arrays are bare lists.
    assert by_name["SIZES"]["__ArrayType__"] == [2, 5]
    # Hashes are dicts with native scalar values.
    assert by_name["OPTS"]["__HashType__"] == {"a": 1, "b": 2}


def test_xml_json_idempotent_round_trip(tmp_path):
    """xml -> json -> xml -> json should reach a fixed point on the JSON side
    (XML side is lossy on the plural-collapse wrapper, which is documented)."""
    src = tmp_path / "in.xml"
    src.write_text(SAMPLE_XML)
    j1 = tmp_path / "first.json"
    x2 = tmp_path / "rt.xml"
    j2 = tmp_path / "second.json"

    xml_json.xml_to_json(str(src), str(j1))
    xml_json.json_to_xml(str(j1), str(x2))
    xml_json.xml_to_json(str(x2), str(j2))

    assert json.loads(j1.read_text()) == json.loads(j2.read_text())


def test_attribute_element_collision_raises(tmp_path):
    # Same name on attribute and child element must raise, not warn-and-drop.
    src = tmp_path / "in.xml"
    src.write_text(
        '<config>\n'
        '  <Item Name="from_attr"><Name>from_child</Name></Item>\n'
        '</config>\n'
    )
    with pytest.raises(ValueError, match=r"name collision on 'Name'"):
        xml_json.xml_to_json(str(src), str(tmp_path / "out.json"))


def test_xml_to_json_no_partial_on_failure(tmp_path):
    # Serialise-time failure must not leave a partial output file.
    src = tmp_path / "in.xml"
    src.write_text(
        '<config>\n'
        '  <Mixed Name="a">stray text<Sub>1</Sub></Mixed>\n'
        '</config>\n'
    )
    dst = tmp_path / "out.json"
    dst.write_text("PRE-EXISTING\n")
    with pytest.raises(ValueError):
        xml_json.xml_to_json(str(src), str(dst))
    assert dst.read_text() == "PRE-EXISTING\n"


def _bin_runs(name: str) -> bool:
    p = _BIN_DIR / name
    return p.exists() and os.access(p, os.X_OK)


@pytest.mark.skipif(
    not (_bin_runs("genesispy-xml2json") and _bin_runs("genesispy-json2xml")),
    reason="bin launchers not installed",
)
def test_bin_launchers_run(tmp_path):
    src = tmp_path / "in.xml"
    src.write_text(SAMPLE_XML)
    mid = tmp_path / "mid.json"
    out = tmp_path / "out.xml"

    env = os.environ.copy()
    env["PYTHON"] = sys.executable
    subprocess.run(
        [str(_BIN_DIR / "genesispy-xml2json"), str(src), str(mid)],
        check=True, env=env,
    )
    assert mid.exists() and json.loads(mid.read_text())
    subprocess.run(
        [str(_BIN_DIR / "genesispy-json2xml"), str(mid), str(out)],
        check=True, env=env,
    )
    assert out.exists() and out.read_text().strip()


# Review 11 #178 -- _native_hash must reject malformed HashItem, not silently skip.
def test_native_hash_raises_on_malformed_hashitem():
    """A HashItem missing its Key must raise, not vanish on round-trip."""
    from genesispy.tools.xml_json import _native_hash

    bad = {"HashItem": [{"Val": "orphan"}]}  # no "Key"
    with pytest.raises(ValueError):
        _native_hash(bad)
