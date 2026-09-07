"""Every ``verilog`` fence in the user guide and code-structure doc is a template
that parses and compiles, unless a ``<!-- fragment -->`` comment precedes it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from genesispy.template.parser import parse_vpy

DOCS = [
    Path(__file__).resolve().parents[1] / "doc" / "user-guide.md",
    Path(__file__).resolve().parents[1] / "doc" / "code-structure.md",
]
_FENCE = re.compile(r"^(<!-- fragment -->\n)?```verilog\n(.*?)^```", re.M | re.S)


def _examples() -> list:
    out = []
    for doc in DOCS:
        text = doc.read_text()
        for m in _FENCE.finditer(text):
            if m.group(1):
                continue
            line = text.count("\n", 0, m.start()) + 1
            out.append(pytest.param(m.group(2), id=f"{doc.name}:{line}"))
    return out


@pytest.mark.parametrize("body", _examples())
def test_guide_verilog_example_parses(body: str, tmp_path: Path) -> None:
    src = tmp_path / "example.vpy"
    src.write_text(body)
    py = parse_vpy(str(src))
    wrapped = "def _exec(self):\n" + "\n".join(
        ("    " + ln if ln.strip() else "") for ln in py.splitlines()
    ) + "\n"
    compile(wrapped, str(src), "exec")
