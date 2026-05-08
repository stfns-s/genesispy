"""Perl-compat generate / generate_base / generate_w_name / clone aliases."""

from __future__ import annotations

import pytest

from genesispy import cache
from genesispy.unique_module import UniqueModule

from ._stubs import StubConfigHandler, StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


class Top(UniqueModule):
    pass


class Leaf(UniqueModule):
    pass


# ------------------------------------------------------- generate dispatch
def test_generate_numeric_dispatches_to_unique_inst() -> None:
    cfg = StubConfigHandler()
    cfg.unq_style = "numeric"
    top = Top(StubManager(cfg_handler=cfg))
    inst = top.generate(Leaf, "u_a", WIDTH=8)
    name = inst.get_unique_module_name()
    # numeric style -> ``Leaf_unq{N}``; param style would mention WIDTH/8.
    assert "_unq" in name
    assert "WIDTH" not in name


def test_generate_param_dispatches_to_unique_inst_param() -> None:
    cfg = StubConfigHandler()
    cfg.unq_style = "param"
    top = Top(StubManager(cfg_handler=cfg))
    inst = top.generate(Leaf, "u_a", WIDTH=8)
    name = inst.get_unique_module_name()
    assert "WIDTH" in name and "8" in name


def test_generate_default_unq_style_is_numeric() -> None:
    # No unq_style attr set on cfg_handler -> default 'numeric'.
    cfg = StubConfigHandler()
    top = Top(StubManager(cfg_handler=cfg))
    inst = top.generate(Leaf, "u_a", WIDTH=8)
    assert "_unq" in inst.get_unique_module_name()


def test_unique_inst_param_sanitises_non_scalar_values() -> None:
    """List-valued param must produce a Verilog-legal `_unique_module_name`."""
    import re as _re
    cfg = StubConfigHandler()
    cfg.unq_style = "param"
    top = Top(StubManager(cfg_handler=cfg))
    inst = top.generate(Leaf, "u_a", LANES=[1, 2, 3])
    name = inst.get_unique_module_name()
    assert _re.fullmatch(r"\w+", name), f"non-identifier name: {name!r}"
    assert "LANES" in name


# ------------------------------------------------------- generate_w_name
class _ManagerWithSynonym(StubManager):
    """StubManager extended with the synonym_class API used by generate_w_name."""

    def __init__(self, cfg_handler=None) -> None:
        super().__init__(cfg_handler=cfg_handler)
        self._classes: dict[str, type] = {}

    def register_class(self, name: str, cls: type) -> None:
        self._classes[name] = cls

    def resolve_module_class(self, name: str) -> type:
        return self._classes[name]

    def synonym_class(self, src_name: str, target_name: str) -> type:
        src_cls = self.resolve_module_class(src_name)
        existing = self._classes.get(target_name)
        if existing is not None:
            if existing is src_cls or issubclass(existing, src_cls):
                return existing
            raise RuntimeError("collision")
        new_cls = type(target_name, (src_cls,), {})
        self._classes[target_name] = new_cls
        return new_cls


def test_generate_w_name_uses_new_base_for_unique_name() -> None:
    mgr = _ManagerWithSynonym()
    mgr.register_class("Leaf", Leaf)
    top = Top(mgr)
    inst = top.generate_w_name("Leaf", "MyLeaf", "u_a", WIDTH=8)
    # Unique name should be derived from gen_module_name, not from base.
    assert inst.get_unique_module_name().startswith("MyLeaf"), (
        inst.get_unique_module_name()
    )
    assert isinstance(inst, Leaf)


def test_generate_w_name_idempotent_for_same_pair() -> None:
    mgr = _ManagerWithSynonym()
    mgr.register_class("Leaf", Leaf)
    top = Top(mgr)
    a = top.generate_w_name("Leaf", "MyLeaf", "u_a")
    b = top.generate_w_name("Leaf", "MyLeaf", "u_b")
    # Same alias class is reused.
    assert type(a) is type(b)


