"""Verilog emitters for the pyinclude_examples demo.

Each takes the module as its first argument. A pyinclude'd file runs with no
``self`` in scope -- a generated module's namespace is shared by every
instance of that template, so a captured module would go stale as soon as
elaboration nested (user-guide section 11.3).
"""

from __future__ import annotations

from typing import Any


def decl_signed(mod: Any, kind: str, width: int, *names: str) -> None:
    """Declare one or more signed vectors of ``width`` bits.

    emit() supplies the newline, so these strings must not carry one.
    """
    for name in names:
        mod.emit(f"   {kind} signed [{width - 1}:0] {name};")


def check_eq(mod: Any, got: str, exp: str, label: str) -> None:
    """Emit a self-check comparing ``got`` against ``exp`` inside a TB loop."""
    mod.emit(f"      if ({got} !== {exp}) begin")
    mod.emit("         errors = errors + 1;")
    mod.emit(
        f'         $display("FAIL {label}: got %0d exp %0d", {got}, {exp});'
    )
    mod.emit("      end")
