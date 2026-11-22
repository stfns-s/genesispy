"""Side outputs: non-Verilog files generated from non-Verilog templates."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from genesispy import cache
from genesispy.cli import parse_args
from genesispy.manager import Manager


FIXTURES = Path(__file__).parent / "fixtures"
SDC = FIXTURES / "side_outputs" / "sdc"
SDC_ARGS = ("--input", str(SDC / "con.sdcpy"), "--extension", ".sdcpy=.sdc:comment=#")


def _run(
    tmp_path: Path, vpy_path: Path, top: str, extra_args: tuple = ()
) -> Manager:
    """Construct a Manager rooted at ``tmp_path`` and run execute()."""
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        args = parse_args(
            ["--input", str(vpy_path), "--top", top, *extra_args]
        )
        m = Manager(args)
        rc = m.execute()
        assert rc == 0, "Manager.execute() should succeed"
        return m
    finally:
        os.chdir(cwd)


def test_extension_comment_in_banner_and_footer(tmp_path):
    _run(tmp_path, SDC / "top.vpy", "top", SDC_ARGS)
    text = cache.OUTFILE_CONTENT_CACHE["con_unq1.sdc"]
    assert text.startswith("# Genesis-Py generated module: con_unq1")
    assert "# Genesis-Py resolved parameter sources:" in text
    assert "//" not in text


def test_other_outputs_keep_global_comment(tmp_path):
    _run(tmp_path, SDC / "top.vpy", "top", SDC_ARGS)
    assert cache.OUTFILE_CONTENT_CACHE["top.v"].startswith("// Genesis-Py")


def test_stdout_dump_separator_uses_extension_comment(tmp_path, capsys):
    _run(tmp_path, SDC / "top.vpy", "top", SDC_ARGS + ("--stdout",))
    out = capsys.readouterr().out
    assert "# genesispy: con_unq1.sdc" in out
    assert "// genesispy: top.v" in out


REG = FIXTURES / "side_outputs" / "reg"
REG_ARGS = ("--src-path", str(REG))
CLI_NOLIST = ("--extension", ".sdcpy=.sdc:nolist:comment=#")


def _run_fail(tmp_path: Path, vpy_path: Path, top: str, extra_args: tuple, capsys) -> str:
    """Run a Manager that must fail; return its stderr."""
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        args = parse_args(["--input", str(vpy_path), "--top", top, *extra_args])
        capsys.readouterr()
        rc = Manager(args).execute()
    finally:
        os.chdir(cwd)
    assert rc == 1
    return capsys.readouterr().err


def test_register_extension_from_template(tmp_path):
    m = _run(tmp_path, REG / "top.vpy", "top", REG_ARGS + ("--vf-out", "top.vf"))
    out = tmp_path / m.verif_dir
    assert (out / "con_unq1.sdc").read_text().startswith("# Genesis-Py")
    vf = (tmp_path / "top.vf").read_text()
    assert "con_unq1.sdc" not in vf and "top.v" in vf


def test_unlisted_absent_from_vlist_and_product_lists(tmp_path):
    m = _run(tmp_path, REG / "top.vpy", "top", REG_ARGS)
    out = tmp_path / m.verif_dir
    assert (out / "con_unq1.sdc").exists()
    for name in ("top.vlist", "top.vlist.verif"):
        text = (tmp_path / m.synth_dir / name).read_text()
        assert "con_unq1.sdc" not in text and "top.v" in text

    prod = tmp_path / "prod"
    prod.mkdir()
    cache.clear_all()
    m = _run(prod, REG / "top.vpy", "top", REG_ARGS + ("--product", "p.vf"))
    out = prod / m.verif_dir
    assert (out / "con_unq1.sdc").exists()
    for name in ("p.vf", "p.synth.vf", "p.verif.vf"):
        text = (prod / name).read_text()
        assert "con_unq1.sdc" not in text, name
    assert "top.v" in (prod / "p.vf").read_text()


def test_unlisted_synonym_file_is_unlisted(tmp_path):
    m = _run(tmp_path, REG / "top_syn.vpy", "top_syn", REG_ARGS + ("--vf-out", "top.vf"))
    out = tmp_path / m.verif_dir
    assert (out / "con_alias.sdc").exists()
    assert "con_alias.sdc" not in (tmp_path / "top.vf").read_text()


def test_cli_form_gives_same_files(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    ma = _run(a, REG / "top.vpy", "top", REG_ARGS + ("--vf-out", "top.vf"))
    sdc_a = (a / ma.verif_dir / "con_unq1.sdc").read_text()
    vf_a = (a / "top.vf").read_text()
    cache.clear_all()
    mb = _run(
        b, REG / "top_nocall.vpy", "top_nocall",
        REG_ARGS + CLI_NOLIST + ("--vf-out", "top.vf"),
    )
    sdc_b = (b / mb.verif_dir / "con_unq1.sdc").read_text()
    assert sdc_a == sdc_b
    vf_b = (b / "top.vf").read_text()
    assert vf_a.replace("top.v", "top_x.v") == vf_b.replace("top_nocall.v", "top_x.v")


def test_cli_nolist_alone_and_comment_alone(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    ma = _run(
        a, REG / "top_nocall.vpy", "top_nocall",
        REG_ARGS + ("--extension", ".sdcpy=.sdc:nolist", "--vf-out", "top.vf"),
    )
    assert (a / ma.verif_dir / "con_unq1.sdc").read_text().startswith("// Genesis-Py")
    assert "con_unq1.sdc" not in (a / "top.vf").read_text()

    cache.clear_all()
    mb = _run(
        b, REG / "top_nocall.vpy", "top_nocall",
        REG_ARGS + ("--extension", ".sdcpy=.sdc:comment=#", "--vf-out", "top.vf"),
    )
    assert (b / mb.verif_dir / "con_unq1.sdc").read_text().startswith("# Genesis-Py")
    assert "con_unq1.sdc" in (b / "top.vf").read_text()


def test_register_conflict_with_cli_raises(tmp_path, capsys):
    err = _run_fail(
        tmp_path, REG / "top_late.vpy", "top_late",
        REG_ARGS + ("--extension", ".sdcpy=.sdc"), capsys,
    )
    assert ".sdcpy" in err


def test_register_remap_default_raises(tmp_path, capsys):
    err = _run_fail(tmp_path, REG / "top_remap.vpy", "top_remap", REG_ARGS, capsys)
    assert ".svpy" in err


def test_register_repeat_and_case_variants_are_noops(tmp_path):
    m = _run(tmp_path, REG / "top_repeat.vpy", "top_repeat", REG_ARGS + ("--vf-out", "top.vf"))
    assert (tmp_path / m.verif_dir / "con_unq1.sdc").read_text().startswith("# Genesis-Py")
    assert "con_unq1.sdc" not in (tmp_path / "top.vf").read_text()


def test_register_empty_comment_raises(tmp_path, capsys):
    err = _run_fail(tmp_path, REG / "top_empty.vpy", "top_empty", REG_ARGS, capsys)
    assert "comment" in err


TEXT = FIXTURES / "side_outputs" / "text"


def test_get_output_text_equals_written_file(tmp_path):
    m = _run(tmp_path, TEXT / "top.vpy", "top", ("--src-path", str(TEXT)))
    out = tmp_path / m.verif_dir
    a, b, c = m._top_inst.texts
    assert a == (out / "leaf_unq1.v").read_text()
    assert b == (out / "leaf_named.v").read_text()
    assert c == a
    assert "endmodule" in a


def test_get_output_text_on_self_raises(tmp_path, capsys):
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        args = parse_args(["--input", str(TEXT / "top_self.vpy"), "--top", "top_self"])
        rc = Manager(args).execute()
    finally:
        os.chdir(cwd)
    assert rc == 1
    assert "not final" in capsys.readouterr().err


def test_get_output_text_includes_footer(tmp_path):
    m = _run(
        tmp_path, TEXT / "top.vpy", "top", ("--src-path", str(TEXT))
    )
    assert "resolved parameter sources:" in m._top_inst.texts[0]


SIDE = FIXTURES / "side_outputs" / "side"
SRC = ("--src-path", str(SIDE))


def _names(path: Path) -> list:
    return [os.path.basename(p) for p in path.read_text().split()]


@pytest.mark.parametrize("vf", [True, False])
def test_side_file_listed_before_its_instance(tmp_path, vf):
    extra = ("--vf-out", "top.vf") if vf else ()
    m = _run(tmp_path, SIDE / "listed.vpy", "listed", SRC + extra)
    path = tmp_path / "top.vf" if vf else tmp_path / m.output_dir / "listed.vlist"
    names = _names(path)
    assert names.index("leaf_hwif.rpt") == names.index("leaf_unq1.v") - 1
    assert (tmp_path / m.verif_dir / "leaf_hwif.rpt").read_text() == "report\n"


def _vf_names(tmp_path, fixture):
    top = Path(fixture).stem
    _run(tmp_path, SIDE / fixture, top, SRC + ("--vf-out", "top.vf"))
    return _names(tmp_path / "top.vf")


def test_side_files_keep_call_order(tmp_path):
    assert _vf_names(tmp_path, "two.vpy") == ["two_b.rpt", "two_a.rpt", "two.v"]


def test_child_output_precedes_parent_side_file(tmp_path):
    assert _vf_names(tmp_path, "blk.vpy") == ["blk_cell.v", "blk.rpt", "blk.v"]


def test_side_file_order_with_clones(tmp_path):
    assert _vf_names(tmp_path, "clones.vpy") == ["cl_unq1.rpt", "cl_unq1.v", "clones.v"]


def test_side_file_package_listed_before_its_user(tmp_path):
    assert _vf_names(tmp_path, "pkguser.svpy") == ["blk_pkg.sv", "pkguser.sv"]


@pytest.mark.skipif(shutil.which("verilator") is None, reason="`verilator` not in PATH")
def test_side_file_package_compiles_from_vf(tmp_path):
    _vf_names(tmp_path, "pkguser.svpy")
    res = subprocess.run(
        ["verilator", "--lint-only", "-f", "top.vf"],
        cwd=tmp_path, capture_output=True, text=True, check=False,
    )
    assert res.returncode == 0, res.stderr


def test_shared_side_file_listed_at_first_writer(tmp_path):
    assert _vf_names(tmp_path, "dup_same.vpy") == [
        "shared.txt", "wa_unq1.v", "wb_unq1.v", "dup_same.v",
    ]


def test_side_file_written_through_parent_precedes_parent(tmp_path):
    assert _vf_names(tmp_path, "pdiscard.vpy") == ["pblk_unq1.v", "u_a.rpt", "pdiscard.v"]


def test_side_file_order_in_product_lists(tmp_path):
    _run(
        tmp_path, SIDE / "listed.vpy", "listed",
        SRC + ("--product", "top.vf", "--synth-top", "listed"),
    )
    for name in ("top.vf", "top.synth.vf"):
        assert _names(tmp_path / name) == ["leaf_hwif.rpt", "leaf_unq1.v", "listed.v"], name


def test_side_file_follows_synth_tag(tmp_path):
    m = _run(tmp_path, SIDE / "listed.vpy", "listed", SRC + ("--synth-top", "listed"))
    assert (tmp_path / m.synth_dir / "leaf_hwif.rpt").read_text() == "report\n"
    assert not (tmp_path / m.verif_dir / "leaf_hwif.rpt").exists()


def test_side_file_unlisted(tmp_path):
    m = _run(
        tmp_path, SIDE / "unlisted.vpy", "unlisted",
        SRC + ("--product", "top.vf", "--synth-top", "unlisted"),
    )
    assert (tmp_path / m.synth_dir / "leaf_hwif.rpt").read_text() == "report\n"
    assert "leaf_nl_unq1.v" in _names(tmp_path / "top.synth.vf")
    for name in ("top.vf", "top.synth.vf", "top.verif.vf"):
        assert "leaf_hwif.rpt" not in (tmp_path / name).read_text(), name


def test_debug_listing_reports_unlisted_side_file(tmp_path, capsys):
    m = _run(tmp_path, SIDE / "unlisted.vpy", "unlisted", SRC + ("--debug", "1"))
    err = capsys.readouterr().err
    assert f"output_writer: wrote unlisted -> {m.verif_dir}/leaf_hwif.rpt" in err
    assert f"output_writer: wrote verif -> {m.verif_dir}/leaf_nl_unq1.v" in err


def test_side_file_unlisted_default_vlist(tmp_path):
    m = _run(tmp_path, SIDE / "unlisted.vpy", "unlisted", SRC)
    assert (tmp_path / m.verif_dir / "leaf_hwif.rpt").exists()
    for path in Path(tmp_path).rglob("*.vlist*"):
        assert "leaf_hwif.rpt" not in path.read_text()


def test_side_file_name_kept(tmp_path):
    m = _run(tmp_path, SIDE / "listed.vpy", "listed", SRC + ("--vf-out", "top.vf"))
    assert not list(Path(tmp_path).rglob("leaf_hwif.rpt.*"))
    assert "leaf_hwif.rpt.v" not in (tmp_path / "top.vf").read_text()
    assert sorted(p.name for p in (tmp_path / m.verif_dir).glob("*.rpt")) == ["leaf_hwif.rpt"]


def test_side_file_with_clones(tmp_path):
    m = _run(tmp_path, SIDE / "clones.vpy", "clones", SRC + ("--vf-out", "top.vf"))
    assert sorted(p.name for p in (tmp_path / m.verif_dir).glob("*.rpt")) == ["cl_unq1.rpt"]
    assert _names(tmp_path / "top.vf").count("cl_unq1.rpt") == 1


def test_side_file_same_text_written_once(tmp_path):
    m = _run(tmp_path, SIDE / "dup_same.vpy", "dup_same", SRC + ("--vf-out", "top.vf"))
    assert (tmp_path / m.verif_dir / "shared.txt").read_text() == "same\n"
    assert _names(tmp_path / "top.vf").count("shared.txt") == 1


def test_side_file_conflicting_text_raises(tmp_path, capsys):
    err = _run_fail(tmp_path, SIDE / "dup_diff.vpy", "dup_diff", SRC, capsys)
    assert "shared.txt" in err
    assert "dup_diff.u_a" in err and "dup_diff.u_b" in err


def test_side_file_conflicting_listed_raises(tmp_path, capsys):
    err = _run_fail(tmp_path, SIDE / "dup_listed.vpy", "dup_listed", SRC, capsys)
    assert "listed" in err
    assert "dup_listed.u_a" in err and "dup_listed.u_b" in err


def test_side_file_vs_template_output_raises(tmp_path, capsys):
    err = _run_fail(tmp_path, SIDE / "vs_output.vpy", "vs_output", SRC, capsys)
    assert "leaf_plain_unq1.v" in err and "template output" in err
    assert "written by vs_output is" in err and "output of vs_output.u_a" in err


@pytest.mark.parametrize("top", ["vs_syn", "vs_named"])
def test_side_file_vs_synonym_and_named_output_raises(tmp_path, capsys, top):
    err = _run_fail(tmp_path, SIDE / f"{top}.vpy", top, SRC, capsys)
    assert "template output of" in err and f"{top}.u_a" in err


def test_synonym_after_side_file_raises(tmp_path, capsys):
    err = _run_fail(tmp_path, SIDE / "syn_after.vpy", "syn_after", SRC, capsys)
    assert "'leaf_alias.v' of syn_after.u_a collides with the side file" in err
    assert "written by syn_after" in err


def test_template_output_after_side_file_raises(tmp_path, capsys):
    err = _run_fail(tmp_path, SIDE / "output_after.vpy", "output_after", SRC, capsys)
    assert "leaf_plain_unq1.v" in err and "side file" in err
    assert "output_after" in err and "u_a" in err


def test_discarded_duplicate_leaves_no_side_file(tmp_path):
    m = _run(tmp_path, SIDE / "discard.vpy", "discard", SRC)
    out = tmp_path / m.verif_dir
    assert sorted(p.name for p in out.glob("*.rpt")) == ["blk_unq1.rpt", "blk_unq2.rpt"]
    assert (out / "blk_unq2.rpt").read_text() == "N=3\n"


def test_side_file_on_finished_child_raises(tmp_path, capsys):
    err = _run_fail(
        tmp_path, SIDE / "on_child.vpy", "on_child", SRC + ("--synth-top", "on_child"), capsys
    )
    assert "write_side_file" in err and "on_child.u_b" in err and "own template" in err


def test_reelaborated_ununique_leaves_no_temp_side_file(tmp_path):
    _run(
        tmp_path, SIDE / "reelab.vpy", "reelab",
        SRC + ("-p", "reelab.u_b.W=4", "--product", "top.vf"),
    )
    files = [p.name for p in tmp_path.rglob("*") if p.is_file()]
    assert "mycell.rpt" in files
    assert not [n for n in files if "mycell_tmp" in n]
    for path in tmp_path.rglob("*"):
        if path.is_file() and path.suffix in (".vf", ".vlist", ".verif", ".depend"):
            assert "mycell_tmp" not in path.read_text(), path.name
            assert "mycell.rpt" not in path.read_text(), path.name


def test_discarded_duplicate_writing_through_parent(tmp_path):
    m = _run(tmp_path, SIDE / "pdiscard.vpy", "pdiscard", SRC)
    out = tmp_path / m.verif_dir
    assert (out / "u_a.rpt").read_text() == "N=2\n"
    assert not list(tmp_path.rglob("u_b.rpt"))


@pytest.mark.parametrize("name", ["../x.rpt", "sub/x.rpt", "x", ""])
def test_side_file_bad_name_raises(tmp_path, name, capsys):
    err = _run_fail(
        tmp_path, SIDE / "badname.vpy", "badname", SRC + ("-p", f"badname.NAME={name}"), capsys
    )
    assert "write_side_file" in err and "bare file name" in err


def test_side_file_non_str_text_raises(tmp_path, capsys):
    err = _run_fail(tmp_path, SIDE / "bytes_text.vpy", "bytes_text", SRC, capsys)
    assert "write_side_file: text of 'x.bin' must be a str, not bytes" in err
    assert not list(tmp_path.rglob("x.bin"))


def test_add_depend_non_str_path_raises(tmp_path, capsys):
    err = _run_fail(tmp_path, SIDE / "bad_depend.vpy", "bad_depend", SRC, capsys)
    assert "add_depend: path must be a str, not int" in err


def test_side_file_mtime_unchanged_on_rerun(tmp_path):
    m = _run(tmp_path, SIDE / "listed.vpy", "listed", SRC)
    path = tmp_path / m.verif_dir / "leaf_hwif.rpt"
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    cache.clear_all()
    _run(tmp_path, SIDE / "listed.vpy", "listed", SRC)
    assert path.stat().st_mtime_ns == 1_000_000_000


def test_side_file_in_stdout_dump(tmp_path, capsys):
    _run(tmp_path, SIDE / "listed.vpy", "listed", SRC + ("--stdout",))
    out = capsys.readouterr().out
    assert "// genesispy: leaf_hwif.rpt\nreport\n" in out
    assert "leaf_hwif.rpt.v" not in out


def test_add_depend_once(tmp_path):
    m = _run(tmp_path, SIDE / "depend.vpy", "depend", SRC)
    text = (tmp_path / m.output_dir / "depend.depend").read_text()
    assert text.splitlines().count("helper.py:") == 1
    assert text.split("\n")[0].split().count("helper.py") == 1


FLOW = FIXTURES / "side_outputs" / "flow"


def test_rdl_flow(tmp_path):
    m = _run(tmp_path, FLOW / "top.vpy", "top", ("--src-path", str(FLOW), "--vf-out", "top.vf"))
    vf = (tmp_path / "top.vf").read_text()
    assert ".rdl" not in vf
    assert "top_regs.sv" in vf
    out = tmp_path / m.verif_dir
    rdl = out / "regs_unq1.rdl"
    assert rdl.exists()
    n_lines = len(rdl.read_text().splitlines())
    assert n_lines > 2
    assert (out / "top_regs.sv").read_text() == f"// core\n// rdl lines: {n_lines}\n"


def test_fixtures_do_not_import_cache():
    for p in (FIXTURES / "side_outputs").rglob("*py"):
        text = p.read_text()
        assert "genesispy.cache" not in text and "import cache" not in text
