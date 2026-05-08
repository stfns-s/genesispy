"""Verify force_param actually pins against later override_param.

interfaces.md states force_param is 'pinned, cannot be re-overridden by
parameter()'. Before this fix, parameter() honoured STATE_FORCED but
override_param() unconditionally clobbered it back to STATE_OVERRIDDEN.
"""

from __future__ import annotations

from ._stubs import StubManager
from genesispy.unique_module import STATE_FORCED, UniqueModule


class _Mod(UniqueModule):
    def execute(self):
        return None


def test_force_param_blocks_subsequent_override_param():
    m = _Mod(StubManager())
    m.define_param("WIDTH", default=8)
    m.force_param("WIDTH", 32)
    assert m.get_param("WIDTH") == 32
    assert m._params["WIDTH"]["state"] == STATE_FORCED

    m.override_param("WIDTH", 64)
    assert m.get_param("WIDTH") == 32
    assert m._params["WIDTH"]["state"] == STATE_FORCED


def test_override_then_force_works_normally():
    m = _Mod(StubManager())
    m.define_param("WIDTH", default=8)
    m.override_param("WIDTH", 16)
    assert m.get_param("WIDTH") == 16

    m.force_param("WIDTH", 32)
    assert m.get_param("WIDTH") == 32
    assert m._params["WIDTH"]["state"] == STATE_FORCED


def test_force_param_blocks_re_force():
    """A second force_param() must not re-pin."""
    m = _Mod(StubManager())
    m.define_param("WIDTH", default=8)
    m.force_param("WIDTH", 32)
    m.force_param("WIDTH", 64)
    assert m.get_param("WIDTH") == 32
    assert m._params["WIDTH"]["state"] == STATE_FORCED


def test_force_param_sets_priority():
    """Bug #2: force_param must record IMMUTABLE priority (Perl parity)."""
    from genesispy.config_handler import Priority

    m = _Mod(StubManager())
    m.define_param("WIDTH", default=8)
    m.force_param("WIDTH", 32)
    assert m._params["WIDTH"]["priority"] == int(Priority.IMMUTABLE)


def test_override_param_sets_priority():
    """Bug #2: override_param (parent-kwarg pass) records INHERITANCE priority."""
    from genesispy.config_handler import Priority

    m = _Mod(StubManager())
    m.define_param("WIDTH", default=8)
    m.override_param("WIDTH", 16)
    assert m._params["WIDTH"]["priority"] == int(Priority.INHERITANCE)
