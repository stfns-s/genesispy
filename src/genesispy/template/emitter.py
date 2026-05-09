"""Emitter: wrap parser output in a complete generated Python module file.

Given the body returned by :func:`genesispy.template.parser.parse_vpy`, the
emitter produces a full Python source file that defines a class derived
from :class:`UniqueModule` and :class:`UserMixin`, with the parsed body as
the body of ``execute()``.

The emitter also (via :func:`write_module`) writes the result to disk and
registers a line map with :mod:`genesispy.template.runtime` so that future
exceptions raised from elaboration can be remapped to .vpy coordinates.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

from .aliases import alias_prelude_source
from .parser import parse_vpy
from . import runtime


__all__ = ["emit_module", "write_module"]


_ALIAS_PRELUDE = alias_prelude_source(indent="        ")


def _header(vpy_path: str, cls_name: str, output_suffix: str) -> str:
    return (
        f"# Auto-generated from {vpy_path} -- DO NOT EDIT\n"
        "from genesispy.template.runtime import UniqueModule, UserMixin, StrCallable\n"
        "from genesispy import user_config as _gpy_user_config\n"
        "\n"
        "\n"
        f"class {cls_name}(UniqueModule, UserMixin):\n"
        f"    _OUTPUT_SUFFIX = {output_suffix!r}\n"
        "\n"
        "    def execute(self):\n"
        "        # Initialize Verilog output buffer + standard banner.\n"
        "        super().execute()\n"
        "        # Perl-compat bare-name aliases (mirror Genesis2's user API).\n"
        f"{_ALIAS_PRELUDE}"
        f"        # ===== body from parse_vpy({vpy_path!r}) =====\n"
    )


_FOOTER = (
    "        # ===========================================\n"
    "        # Re-flush after body emit() calls (overwrites base-class flush).\n"
    "        self._flush_outfile()\n"
)


def _module_name_from_path(vpy_path: str) -> str:
    stem = os.path.splitext(os.path.basename(vpy_path))[0]
    # Sanitize: Python identifier-safe.
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in stem)
    if safe and safe[0].isdigit():
        safe = "_" + safe
    return safe or "GeneratedModule"


def emit_module(
    vpy_path: str,
    parsed_body: str,
    *,
    module_name: Optional[str] = None,
    output_suffix: str = ".v",
) -> str:
    """Return Python source for a complete generated module file.

    ``parsed_body`` is the column-zero output of :func:`parse_vpy`; it is
    indented eight spaces (one level for ``class``, one for ``def execute``)
    before insertion.  ``# line N "file.vpy"`` directives are preserved
    verbatim (as Python comments). ``output_suffix`` is stamped on the
    generated class as ``_OUTPUT_SUFFIX`` so flush-time consumers
    (``UniqueModule._flush_outfile`` / ``synonym``) know which Verilog
    extension to emit without consulting the Manager.
    """
    cls_name = module_name or _module_name_from_path(vpy_path)
    indent = "        "  # 8 spaces

    if parsed_body:
        body_lines = parsed_body.splitlines()
        # Indent every non-empty line; preserve empty lines as-is.
        indented = "\n".join(
            (indent + ln) if ln.strip() else ln for ln in body_lines
        )
        if not indented.endswith("\n"):
            indented += "\n"
    else:
        indented = indent + "pass\n"

    return _header(vpy_path, cls_name, output_suffix) + indented + _FOOTER


def write_module(
    vpy_path: str,
    output_dir: str,
    *,
    output_suffix: str = ".v",
    allowed: Optional[Iterable[str]] = None,
    syntax: str = "genesis",
    comment: str = "//",
) -> str:
    """Parse ``vpy_path``, emit, write to ``<output_dir>/<stem>.py``.

    Returns the absolute path of the generated .py file.  Side-effect:
    builds a line map from the generated source and registers it with
    :mod:`genesispy.template.runtime`.

    ``output_suffix`` is the Verilog extension paired with this input; it
    is stamped onto the generated class. ``allowed`` is forwarded to
    :func:`parse_vpy` for input-extension validation (defaults to the
    built-in ``.vpy``/``.svpy`` set). ``syntax`` selects the directive
    flavour (``"genesis"`` or ``"jinja2"``).
    """
    os.makedirs(output_dir, exist_ok=True)
    body = parse_vpy(vpy_path, allowed, syntax=syntax, comment=comment)
    src = emit_module(vpy_path, body, output_suffix=output_suffix)

    stem = _module_name_from_path(vpy_path)
    out_path = os.path.abspath(os.path.join(output_dir, f"{stem}.py"))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(src)

    mapping = runtime.build_line_map(src)
    runtime.register_line_map(out_path, mapping)
    return out_path
