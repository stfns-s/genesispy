"""Unit tests for genesispy.output_writer (Wave-2 Phase E)."""

from __future__ import annotations

import io
import os
import stat
import subprocess
import sys

import pytest

from genesispy import cache, output_writer

from ._stubs import StubManager


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_cache():
    cache.clear_all()
    yield
    cache.clear_all()


@pytest.fixture
def manager(tmp_path):
    m = StubManager()
    m.top = "my_top"
    m.output_dir = str(tmp_path)
    m.raw_dir = str(tmp_path / "raw")
    m.synth_dir = str(tmp_path / "synth")
    m.verif_dir = str(tmp_path / "verif")
    m.src_path = [str(tmp_path / "src" / "foo.vpy"),
                  str(tmp_path / "src" / "bar.vpy")]
    return m


def _populate_cache():
    """Two synth-tagged modules + one verif-tagged (testbench) module.

    Tags now drive partitioning (``cache.OUTFILE_TAGS``) instead of the
    old ``_tb`` filename heuristic, mirroring Perl path-based tagging
    in ``Manager.pm:1330-1395``.
    """
    cache.OUTFILE_CONTENT_CACHE["alu"] = "module alu; endmodule\n"
    cache.OUTFILE_CONTENT_CACHE["regfile.v"] = "module regfile; endmodule\n"
    cache.OUTFILE_CONTENT_CACHE["alu_tb.v"] = "module alu_tb; endmodule\n"
    cache.OUTFILE_TAGS["alu"] = "synth"
    cache.OUTFILE_TAGS["regfile.v"] = "synth"
    cache.OUTFILE_TAGS["alu_tb.v"] = "verif"


# --------------------------------------------------------------------------- #
# flush_to_disk
# --------------------------------------------------------------------------- #


def test_flush_partitions_by_tag(manager):
    _populate_cache()
    written = output_writer.flush_to_disk(manager)

    assert sorted(os.path.basename(p) for p in written["synth"]) == [
        "alu.v", "regfile.v",
    ]
    assert sorted(os.path.basename(p) for p in written["verif"]) == ["alu_tb.v"]
    assert written["synth_and_verif"] == []

    for p in written["synth"]:
        assert os.path.isfile(p)
        assert os.path.dirname(p) == manager.synth_dir
    for p in written["verif"]:
        assert os.path.isfile(p)
        assert os.path.dirname(p) == manager.verif_dir

    # Content matches cache, with .v normalisation.
    with open(os.path.join(manager.synth_dir, "alu.v")) as fh:
        assert fh.read() == "module alu; endmodule\n"


def test_flush_defaults_unmapped_files_to_verif(manager):
    """No tag map -> Perl SynthTop=undef behaviour: every file is verif."""
    cache.OUTFILE_CONTENT_CACHE["alu.v"] = "module alu; endmodule\n"
    cache.OUTFILE_CONTENT_CACHE["regfile.v"] = "module regfile; endmodule\n"
    written = output_writer.flush_to_disk(manager)
    assert sorted(os.path.basename(p) for p in written["verif"]) == [
        "alu.v", "regfile.v",
    ]
    assert written["synth"] == []


def test_flush_synth_and_verif_lands_in_synth_dir(manager):
    cache.OUTFILE_CONTENT_CACHE["shared.v"] = "module shared; endmodule\n"
    cache.OUTFILE_TAGS["shared.v"] = "synth_and_verif"
    written = output_writer.flush_to_disk(manager)
    assert os.path.join(manager.synth_dir, "shared.v") in written["synth_and_verif"]
    assert written["synth"] == []
    assert written["verif"] == []
    assert os.path.isfile(os.path.join(manager.synth_dir, "shared.v"))


def test_flush_is_idempotent(manager):
    _populate_cache()
    output_writer.flush_to_disk(manager)

    target = os.path.join(manager.synth_dir, "alu.v")
    mtime_before = os.path.getmtime(target)

    # Second flush with identical cache contents should not rewrite.
    # Sleep-free check: write a sentinel mtime in the past, then verify it
    # is unchanged.
    past = mtime_before - 100
    os.utime(target, (past, past))

    output_writer.flush_to_disk(manager)
    assert os.path.getmtime(target) == past, "idempotent flush must skip rewrite"


def test_flush_rewrites_when_cache_content_changes(manager):
    _populate_cache()
    output_writer.flush_to_disk(manager)
    target = os.path.join(manager.synth_dir, "alu.v")

    cache.OUTFILE_CONTENT_CACHE["alu"] = "module alu; // edited\nendmodule\n"
    output_writer.flush_to_disk(manager)
    with open(target) as fh:
        assert "// edited" in fh.read()


@pytest.mark.parametrize(
    "scenario,use_output_dir,flavor",
    [
        ("empty_dirs_fallback", False, "both"),
        ("same_dir_collision",  True,  "both"),
        ("flavor_filter_runs_after_collision", True, "synth"),
    ],
)
def test_flush_warns_on_synth_verif_collision(
    manager, capsys, scenario, use_output_dir, flavor,
):
    """synth/verif tags collide on the same emitted basename — must warn.

    Three configurations exercise the same warning path: empty synth/verif
    dirs falling back to output_dir, explicit shared output_dir, and the
    same shared dir under a non-default --flavor (collision detection must
    run before the flavor filter drops one side).
    """
    cache.OUTFILE_CONTENT_CACHE["alu"] = "module alu_synth; endmodule\n"
    cache.OUTFILE_CONTENT_CACHE["alu.v"] = "module alu_verif; endmodule\n"
    cache.OUTFILE_TAGS["alu"] = "synth"
    cache.OUTFILE_TAGS["alu.v"] = "verif"
    manager.synth_dir = manager.output_dir if use_output_dir else ""
    manager.verif_dir = manager.output_dir if use_output_dir else ""
    manager.out_type = flavor
    output_writer.flush_to_disk(manager)
    err = capsys.readouterr().err
    assert "alu.v" in err and "overwrite" in err


def test_flush_gen_raw_writes_all_files_regardless_of_flavor(manager):
    """``--gen-raw`` dumps the full elaborated set into raw_dir regardless of --flavor."""
    _populate_cache()  # 2 synth + 1 verif
    manager.gen_raw = True
    manager.out_type = "synth"  # would otherwise drop the verif file
    written = output_writer.flush_to_disk(manager)

    # Main output respects the filter.
    assert sorted(os.path.basename(p) for p in written["verif"]) == []

    # raw_dir contains every elaborated file, including the verif one.
    raw_files = sorted(os.listdir(manager.raw_dir))
    assert raw_files == ["alu.v", "alu_tb.v", "regfile.v"]


def test_flush_tag_map_drives_partition(manager):
    """``cache.OUTFILE_TAGS`` overrides the default 'verif' for unmapped."""
    cache.OUTFILE_CONTENT_CACHE["alu"] = "module alu; endmodule\n"
    cache.OUTFILE_CONTENT_CACHE["alu_tb.v"] = "module alu_tb; endmodule\n"
    cache.OUTFILE_TAGS["alu"] = "verif"
    cache.OUTFILE_TAGS["alu_tb.v"] = "synth"
    written = output_writer.flush_to_disk(manager)
    assert os.path.join(manager.verif_dir, "alu.v") in written["verif"]
    assert os.path.join(manager.synth_dir, "alu_tb.v") in written["synth"]


# --------------------------------------------------------------------------- #
# write_file_lists
# --------------------------------------------------------------------------- #


def test_write_file_lists_creates_vlist_and_depend(manager):
    _populate_cache()
    written = output_writer.flush_to_disk(manager)
    out = output_writer.write_file_lists(manager, written)

    synth_vlist = os.path.join(manager.output_dir, "my_top.vlist")
    verif_vlist = os.path.join(manager.output_dir, "my_top.vlist.verif")
    depend = os.path.join(manager.output_dir, "my_top.depend")

    assert out["synth_vlist"] == synth_vlist
    assert out["verif_vlist"] == verif_vlist
    assert out["depend"] == depend

    with open(synth_vlist) as fh:
        lines = fh.read().splitlines()
    # `<top>.vlist` is the FULL list (synth + verif + synth_and_verif),
    # mirroring Perl's $product_fh.  Three files in the populated cache.
    assert len(lines) == 3
    assert all(line.endswith(".v") for line in lines)
    assert any("alu.v" in line for line in lines)
    assert any("regfile.v" in line for line in lines)
    assert any("alu_tb.v" in line for line in lines)

    with open(verif_vlist) as fh:
        verif_lines = fh.read().splitlines()
    assert len(verif_lines) == 1
    assert verif_lines[0].endswith("alu_tb.v")

    with open(depend) as fh:
        depend_body = fh.read()
    assert depend_body.startswith(_basename_match(synth_vlist) + ":") or \
        synth_vlist in depend_body
    assert "foo.vpy" in depend_body
    assert "bar.vpy" in depend_body


def _basename_match(path: str) -> str:
    # tests/_stubs lives near tmp_path, but vlist content uses relpath from
    # cwd at write time — so we just reuse the same helper.
    return os.path.relpath(path, start=os.getcwd())


def test_write_file_lists_omits_verif_when_empty(manager):
    cache.OUTFILE_CONTENT_CACHE["alu.v"] = "module alu; endmodule\n"
    cache.OUTFILE_TAGS["alu.v"] = "synth"
    written = output_writer.flush_to_disk(manager)
    out = output_writer.write_file_lists(manager, written)
    assert "verif_vlist" not in out
    assert not os.path.exists(os.path.join(manager.output_dir,
                                           "my_top.vlist.verif"))


# --------------------------------------------------------------------------- #
# write_clean_script
# --------------------------------------------------------------------------- #


def test_write_clean_script_creates_executable(manager):
    _populate_cache()
    written = output_writer.flush_to_disk(manager)
    output_writer.write_file_lists(manager, written)

    script_path = output_writer.write_clean_script(manager)
    assert os.path.isfile(script_path)

    mode = os.stat(script_path).st_mode
    assert mode & stat.S_IXUSR, "owner exec bit must be set"
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH

    with open(script_path) as fh:
        body = fh.read()
    assert body.startswith("#!/bin/sh")
    assert manager.synth_dir in body
    assert manager.verif_dir in body
    assert manager.raw_dir in body
    assert "my_top.vlist" in body


@pytest.mark.skipif(sys.platform.startswith("win"), reason="needs /bin/sh")
def test_clean_script_quotes_paths_with_special_chars(tmp_path, manager):
    """Review10 #91: clean-script paths must be shell-quoted so that
    embedded $/`/" don't break or inject into the generated script."""
    weird = tmp_path / 'odd dir $name "q"'
    weird.mkdir()
    manager.output_dir = str(weird)
    manager.synth_dir = str(weird / "synth")
    manager.verif_dir = str(weird / "verif")
    manager.raw_dir = str(weird / "raw")
    for d in (manager.synth_dir, manager.verif_dir, manager.raw_dir):
        os.makedirs(d, exist_ok=True)
    cache.OUTFILE_CONTENT_CACHE["alu.v"] = "module alu; endmodule\n"
    cache.OUTFILE_TAGS["alu.v"] = "synth"
    output_writer.flush_to_disk(manager)
    output_writer.write_file_lists(manager, {"synth": [], "verif": [], "synth_and_verif": []})
    script_path = output_writer.write_clean_script(manager)
    # Run it; should not error.
    subprocess.run(["/bin/sh", script_path], check=True)
    # synth_dir should be removed.
    assert not os.path.exists(manager.synth_dir)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="needs /bin/sh")
def test_clean_script_executes_and_removes_dirs(manager):
    _populate_cache()
    # ensure raw_dir actually exists (flush_to_disk does not create it)
    os.makedirs(manager.raw_dir, exist_ok=True)
    written = output_writer.flush_to_disk(manager)
    output_writer.write_file_lists(manager, written)
    script = output_writer.write_clean_script(manager)

    assert os.path.isdir(manager.synth_dir)
    subprocess.run(["/bin/sh", script], check=True)

    assert not os.path.isdir(manager.synth_dir)
    assert not os.path.isdir(manager.verif_dir)
    assert not os.path.isdir(manager.raw_dir)
    assert not os.path.isfile(os.path.join(manager.output_dir, "my_top.vlist"))
    assert not os.path.isfile(script)


# --------------------------------------------------------------------------- #
# clean_outputs
# --------------------------------------------------------------------------- #


def test_clean_outputs_removes_everything(manager):
    _populate_cache()
    os.makedirs(manager.raw_dir, exist_ok=True)
    written = output_writer.flush_to_disk(manager)
    output_writer.write_file_lists(manager, written)
    output_writer.write_clean_script(manager)

    output_writer.clean_outputs(manager)

    assert not os.path.isdir(manager.synth_dir)
    assert not os.path.isdir(manager.verif_dir)
    assert not os.path.isdir(manager.raw_dir)
    assert not os.path.isfile(os.path.join(manager.output_dir, "my_top.vlist"))
    assert not os.path.isfile(os.path.join(manager.output_dir,
                                           "my_top.vlist.verif"))
    assert not os.path.isfile(os.path.join(manager.output_dir, "my_top.depend"))


def test_clean_outputs_tolerant_of_missing_dirs(manager):
    # Nothing was ever written. Should not raise.
    output_writer.clean_outputs(manager)


def test_dump_to_stdout_concatenates_with_separators(manager):
    cache.OUTFILE_CONTENT_CACHE["alpha"] = "module alpha; endmodule\n"
    cache.OUTFILE_CONTENT_CACHE["beta"] = "module beta; endmodule"  # no trailing \n
    buf = io.StringIO()
    output_writer.dump_to_stdout(manager, stream=buf)
    out = buf.getvalue()
    assert "// genesispy: alpha.v\n" in out
    assert "// genesispy: beta.v\n" in out
    assert "module alpha; endmodule" in out
    assert "module beta; endmodule" in out
    # beta lacks trailing newline; dump_to_stdout must add one.
    assert out.endswith("\n")


# Idempotency guard: _write_if_changed must not rewrite identical content
# on a second call, including under CRLF (`newline=` semantics on Python's
# text-mode open are read=write here, so this is the trivial case).
def test_write_if_changed_idempotent_under_crlf(tmp_path):
    p = str(tmp_path / "crlf.txt")
    content = "a\r\nb\r\n"
    assert output_writer._write_if_changed(p, content) is True
    assert output_writer._write_if_changed(p, content) is False


# Review 11 #176 -- generated clean script must dedup overlapping target dirs.
def test_write_clean_script_dedups_overlapping_dirs(tmp_path):
    """When --synth-dir and --verif-dir collide, the script must dedup rm -rf."""
    m = StubManager()
    m.top = "my_top"
    m.output_dir = str(tmp_path)
    m.raw_dir = ""
    shared = str(tmp_path / "shared")
    m.synth_dir = shared
    m.verif_dir = shared
    output_writer.write_clean_script(m)
    body = (tmp_path / "genesispy_clean.sh").read_text()
    assert body.count(f"rm -rf {shared}") <= 1, (
        f"duplicate rm -rf for {shared!r} in clean script:\n{body}"
    )


def test_dump_to_stdout_emits_top_last(manager):
    manager.top = "my_top"
    cache.OUTFILE_CONTENT_CACHE["aaa"] = "// aaa\n"
    cache.OUTFILE_CONTENT_CACHE["my_top"] = "// top\n"
    cache.OUTFILE_CONTENT_CACHE["zzz"] = "// zzz\n"
    buf = io.StringIO()
    output_writer.dump_to_stdout(manager, stream=buf)
    out = buf.getvalue()
    assert out.index("// aaa") < out.index("// zzz") < out.index("// top")


# Review 11 #196 -- StubManager must expose every attribute interfaces.md declares public.
def test_stub_manager_has_documented_attrs():
    s = StubManager()
    for attr in ("synth_top", "synth_dir", "verif_dir", "raw_dir",
                 "output_dir", "extension_map", "top", "cfg_handler"):
        assert hasattr(s, attr), f"StubManager missing {attr!r}"


# --------------------------------------------------------------------------- #
# write_product_lists -- --product (.synth/.verif) and --vf-out (.synth.vf/.verif.vf)
# --------------------------------------------------------------------------- #


def test_write_product_lists_no_extension(manager, tmp_path):
    """--product FILE with no extension writes FILE / FILE.synth / FILE.verif."""
    _populate_cache()
    written = output_writer.flush_to_disk(manager)
    base = str(tmp_path / "manifest")
    out = output_writer.write_product_lists(manager, written, base)
    # Cluster J2: triple-file output (master + synth + verif).
    assert out["master"] == base
    assert out["synth"] == base + ".synth"
    assert out["verif"] == base + ".verif"
    for k in ("master", "synth", "verif"):
        assert os.path.isfile(out[k])


def test_write_product_lists_with_extension(manager, tmp_path):
    """--product FILE.ext writes FILE.ext / FILE.synth.ext / FILE.verif.ext.

    Mirrors Perl Manager.pm:1302-1319 (last-dot extension split).
    """
    _populate_cache()
    written = output_writer.flush_to_disk(manager)
    base = str(tmp_path / "manifest.vf")
    out = output_writer.write_product_lists(manager, written, base)
    stem = str(tmp_path / "manifest")
    assert out["master"] == base
    assert out["synth"] == stem + ".synth.vf"
    assert out["verif"] == stem + ".verif.vf"
    for k in ("master", "synth", "verif"):
        assert os.path.isfile(out[k])
