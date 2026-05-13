"""Cluster C: parameter() kwargs (force/doc/min/max/step/list/opt) plus
range guard, doc_param, and param_range.

Mirrors Perl ``parameter`` / ``doc_param`` / ``param_range``
(UniqueModule.pm:1981 / :558 / :582).
"""

from __future__ import annotations

import pytest

from genesispy import cache
from genesispy.reporting import ParameterError
from genesispy.unique_module import UniqueModule

from ._stubs import StubManager


def setup_function(_fn) -> None:
    cache.clear_all()


class _Mod(UniqueModule):
    pass


# ----------------------------------------------------- parameter(force=...)


def test_parameter_force_writes_at_forced_priority() -> None:
    inst = _Mod(StubManager())
    inst.parameter("WIDTH", 32, force=True)
    # FORCED state pins the value against later override.
    inst.override_param("WIDTH", 64)
    assert inst.get_param("WIDTH") == 32


# ----------------------------------------------------- parameter(doc=...)


def test_parameter_doc_kwarg_stores_documentation() -> None:
    inst = _Mod(StubManager())
    inst.parameter("WIDTH", 8, doc="bit width of the bus")
    assert inst._params["WIDTH"]["doc"] == "bit width of the bus"


# --------------------------- parameter(min=, max=, step=) range guard


def test_parameter_min_max_within_range_ok() -> None:
    inst = _Mod(StubManager())
    val = inst.parameter("BitWidth", 16, min=1, max=64)
    assert val == 16


def test_parameter_min_violation_raises() -> None:
    inst = _Mod(StubManager())
    with pytest.raises(ParameterError, match="below min"):
        inst.parameter("BitWidth", -1, min=0, max=64)


def test_parameter_max_violation_raises() -> None:
    inst = _Mod(StubManager())
    with pytest.raises(ParameterError, match="above max"):
        inst.parameter("BitWidth", 99, min=0, max=64)


# ----------------------------------------------- parameter(list=...)


def test_parameter_list_membership_ok() -> None:
    inst = _Mod(StubManager())
    val = inst.parameter("Enc", "gray", list=["binary", "gray", "onehot"])
    assert val == "gray"


def test_parameter_list_membership_violation_raises() -> None:
    inst = _Mod(StubManager())
    with pytest.raises(ParameterError, match="not in allowed list"):
        inst.parameter("Enc", "martian", list=["binary", "gray", "onehot"])


def test_parameter_minmax_xor_list_raises() -> None:
    inst = _Mod(StubManager())
    with pytest.raises(ParameterError, match="cannot combine"):
        inst.parameter("Foo", 1, min=0, max=10, list=[1, 2, 3])


# --------------------------------------------------- range re-check on override


def test_override_param_rechecks_range() -> None:
    inst = _Mod(StubManager())
    inst.parameter("BitWidth", 8, min=0, max=64)
    with pytest.raises(ParameterError, match="above max"):
        inst.override_param("BitWidth", 999)


def test_force_param_rechecks_range() -> None:
    inst = _Mod(StubManager())
    inst.parameter("BitWidth", 8, min=0, max=64)
    with pytest.raises(ParameterError, match="above max"):
        inst.force_param("BitWidth", 999)


# ---------------------------------------------------- parameter(opt=...)


def test_parameter_opt_store_only() -> None:
    inst = _Mod(StubManager())
    inst.parameter("WIDTH", 8, opt="try")
    assert inst._params["WIDTH"]["opt"] == "try"


def test_parameter_opt_invalid_raises() -> None:
    inst = _Mod(StubManager())
    with pytest.raises(ParameterError, match="yes"):
        inst.parameter("WIDTH", 8, opt="maybe")


# -------------------------------------------------------- doc_param late-bind


def test_doc_param_sets_documentation() -> None:
    inst = _Mod(StubManager())
    inst.parameter("WIDTH", 8)
    inst.doc_param("WIDTH", "bus width")
    assert inst._params["WIDTH"]["doc"] == "bus width"


def test_doc_param_on_unknown_raises() -> None:
    inst = _Mod(StubManager())
    with pytest.raises(ParameterError, match="un-existing parameter"):
        inst.doc_param("NOPE", "msg")


def test_doc_param_redoc_warns(capsys) -> None:
    inst = _Mod(StubManager())
    inst.parameter("WIDTH", 8, doc="first")
    inst.doc_param("WIDTH", "second")
    err = capsys.readouterr().err
    assert "Re-documentation" in err
    assert inst._params["WIDTH"]["doc"] == "second"


# --------------------------------------------------------- param_range late-bind


def test_param_range_late_bind_checks_current_value() -> None:
    inst = _Mod(StubManager())
    inst.parameter("WIDTH", 5)
    inst.param_range("WIDTH", min=0, max=10)
    # Value 5 is within [0,10]; no error.
    assert inst.get_param("WIDTH") == 5


def test_param_range_late_bind_raises_on_violating_value() -> None:
    inst = _Mod(StubManager())
    inst.parameter("WIDTH", 99)
    with pytest.raises(ParameterError, match="above max"):
        inst.param_range("WIDTH", min=0, max=10)


def test_param_range_on_unknown_raises() -> None:
    inst = _Mod(StubManager())
    with pytest.raises(ParameterError, match="un-existing parameter"):
        inst.param_range("NOPE", min=0, max=10)


def test_param_range_redefinition_raises() -> None:
    inst = _Mod(StubManager())
    inst.parameter("WIDTH", 5, min=0, max=10)
    with pytest.raises(ParameterError, match="Re-definition of range"):
        inst.param_range("WIDTH", min=0, max=20)
