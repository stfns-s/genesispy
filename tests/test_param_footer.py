"""``--param-footer``: the provenance block appended after a generated module."""

from __future__ import annotations

import re

import pytest

from genesispy.config_handler import Priority
from genesispy.unique_module import (
    _PARAM_FOOTER_VALUE_WIDTH,
    UniqueModule,
    _comparable_lines,
)

from ._stubs import StubManager


class Top(UniqueModule):
    pass


# ------------------------------------------------ --param-footer provenance
def _footer_of(mod: UniqueModule) -> str:
    """Return only the text ``emit_param_footer`` appended to the buffer."""
    before = mod._outfile_handle.getvalue() if mod._outfile_handle else ""
    mod.emit_param_footer()
    after = mod._outfile_handle.getvalue() if mod._outfile_handle else ""
    return after[len(before):]


def _five_provenance_module(mgr: StubManager) -> UniqueModule:
    """A module carrying one parameter per rung of the Priority ladder."""
    top = Top(mgr)
    top.define_param("AWIDTH", default=5)                 # declaration default
    top.override_param("NAME", "rf0")                     # parent instantiation
    top.force_param("PIPELINE", True)                     # forced
    for name, value, prio in (
        ("DEPTH", 32, Priority.CMD_LINE),
        ("DWIDTH", 32, Priority.EXTERNAL_PARAM_FILE),
        ("CFGVAL", 1, Priority.EXTERNAL_CONFIG),
    ):
        top.define_param(name, default=value)
        top._params[name]["state"] = "OVERRIDDEN"
        top._params[name]["priority"] = int(prio)
    return top


def test_param_footer_off_by_default() -> None:
    """Without --param-footer the method appends nothing."""
    mgr = StubManager()
    top = Top(mgr)
    top.define_param("N", default=8)
    assert _footer_of(top) == ""


def test_param_footer_skipped_when_no_params() -> None:
    """A module with no parameters gets no header line either."""
    mgr = StubManager()
    mgr.param_footer = True
    top = Top(mgr)
    assert _footer_of(top) == ""


def test_param_footer_reports_every_provenance() -> None:
    """Each Priority rung renders its own source label."""
    mgr = StubManager()
    mgr.param_footer = True
    footer = _footer_of(_five_provenance_module(mgr))
    assert "// Genesis-Py resolved parameter provenance" in footer
    assert re.search(r"^//\s+AWIDTH\s+: 5\s+<- declaration default$", footer, re.M)
    assert re.search(r"^//\s+CFGVAL\s+: 1\s+<- config script", footer, re.M)
    assert re.search(r"^//\s+DEPTH\s+: 32\s+<- command line", footer, re.M)
    assert re.search(r"^//\s+DWIDTH\s+: 32\s+<- config file", footer, re.M)
    assert re.search(r"^//\s+NAME\s+: 'rf0'\s+<- parent instantiation$", footer, re.M)
    assert re.search(r"^//\s+PIPELINE\s+: True\s+<- forced", footer, re.M)


def test_param_footer_honours_output_comment_block_style() -> None:
    """(open, close) wraps the footer with delimiters on their own lines."""
    mgr = StubManager()
    mgr.param_footer = True
    mgr.output_comment = ("/*", "*/")
    top = Top(mgr)
    top.define_param("N", default=8)
    lines = _footer_of(top).splitlines()
    assert lines[0] == "/*"
    assert lines[-1] == "*/"
    assert " Genesis-Py resolved parameter provenance" in lines
    assert "//" not in "\n".join(lines)


def test_param_footer_avoids_parity_header_shape() -> None:
    """The footer must not look like a banner parameter row.

    tests/_parity_normalize.parse_header scans for '// NAME = value' rows and
    its window is unbounded on files with no 'module' keyword, so a footer
    using '=' would corrupt the parsed parameter signature.
    """
    mgr = StubManager()
    mgr.param_footer = True
    footer = _footer_of(_five_provenance_module(mgr))
    assert "Parameters:" not in footer
    assert re.search(r"^\s*//\s+\w+\s*=", footer, re.M) is None


@pytest.mark.parametrize("style", ["//", ("/*", "*/")])
def test_param_footer_is_invisible_to_comparable_lines(style) -> None:
    """_compare_generated_files must not see the footer as content.

    ununique_inst re-elaborates and diffs via _comparable_lines; a footer that
    survived that stripping would make identical modules compare unequal.
    """
    mgr = StubManager()
    mgr.output_comment = style
    top = Top(mgr)
    top.define_param("N", default=8)
    top.emit("module Top ();")
    top.emit("endmodule")
    without = top._outfile_handle.getvalue()
    mgr.param_footer = True
    top.emit_param_footer()
    with_footer = top._outfile_handle.getvalue()
    assert with_footer != without
    assert _comparable_lines(with_footer, style) == _comparable_lines(without, style)


def test_param_footer_caps_the_value_column() -> None:
    """One long repr must not pad every other row out to its width."""
    mgr = StubManager()
    mgr.param_footer = True
    top = Top(mgr)
    top.define_param("N", default=8)
    top.define_param("BIG", default={f"key{i}": i for i in range(12)})
    row_n = next(ln for ln in _footer_of(top).splitlines() if " N " in ln)
    # The short value is padded to the cap, not to the long repr's width.
    assert f"{'8':<{_PARAM_FOOTER_VALUE_WIDTH}}  <- " in row_n
