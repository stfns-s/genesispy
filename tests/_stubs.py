"""Lightweight stand-ins for Manager/ConfigHandler used by unit tests.

These avoid a hard dependency on the real implementations in sibling
modules.
"""

from __future__ import annotations

import types
from typing import Any, Dict, Optional


class StubConfigHandler:
    """Minimal ConfigHandler shim: configurable-key lookup, otherwise None."""

    # Class attribute so consumers can read ``cfg.unq_style`` directly
    # (matches the real ConfigHandler instance attribute).
    unq_style: str = "numeric"

    def __init__(self, values: Optional[Dict[str, Any]] = None) -> None:
        self._values: Dict[str, Any] = dict(values or {})

    # Match doc/interfaces.md ConfigHandler API surface used by UniqueModule.
    def get_param_val(self, name: str) -> Any:
        return None

    def get_cfg_param_val(self, name: str) -> Any:
        return None

    def get_cmdln_param_val(self, name: str) -> Any:
        return None

    def configure(self, name: str, value: Any, **flags: Any) -> None:
        self._values[name] = value

    def get_configuration(
        self, name: str, *, instance_path: Any = None
    ) -> Any:
        return self._values.get(name)

    def get_configuration_with_priority(
        self, name: str, *, instance_path: Any = None
    ) -> tuple:
        return (self._values.get(name), None)

    def exists_configuration(
        self, name: str, *, instance_path: Any = None
    ) -> bool:
        return name in self._values

    def remove_configuration(self, name: str) -> None:
        self._values.pop(name, None)

    def print_configuration(self) -> str:
        return repr(self._values)

    def cmdln_db_snapshot(self) -> Dict[str, dict]:
        return {}

    def cfg_db_snapshot(self) -> Dict[str, dict]:
        return {}

    def cmdln_scoped_db_snapshot(self) -> Dict[tuple, dict]:
        return {}


class StubManager:
    """Bare attribute container mirroring the public Manager surface."""

    def __init__(
        self,
        cfg_handler: Optional[StubConfigHandler] = None,
        debug: int = 0,
        extension_map: Optional[Dict[str, str]] = None,
    ) -> None:
        self.cfg_handler = cfg_handler or StubConfigHandler()
        self.top: Optional[str] = None
        self.synth_top: Optional[str] = None
        self.debug: int = debug
        self.src_path: list = []
        self.parsed_source_files: list = []
        self.inc_path: list = []
        self.cfg_path: list = []
        self.output_dir: str = ""
        self.raw_dir: str = ""
        self.synth_dir: str = ""
        self.verif_dir: str = ""
        from genesispy.extensions import DEFAULT_EXTENSION_MAP
        self.extension_map: Dict[str, str] = dict(
            extension_map if extension_map is not None else DEFAULT_EXTENSION_MAP
        )
        # Required by ConfigHandler/UniqueModule/output_writer consumers.
        self.args = types.SimpleNamespace(parameter=[], unq_style=None)
        self.no_module_cache: bool = False
        self.out_type: str = "both"
        self.gen_raw: bool = False
        self.depend_file: Optional[str] = None
        self.product_file: Optional[str] = None
        self.product_single: bool = False
        self.touched_dirs: list = []
        self.syntax: str = "genesis"
        self.source_comment: str = "//"
        self.output_comment: str = "//"
        self.param_footer: bool = False

    def find_file(self, name: str, paths=None) -> str:  # pragma: no cover
        raise FileNotFoundError(name)

    def execute(self) -> int:  # pragma: no cover
        return 0

    def _resolve_cfg_path(self, name: str) -> Optional[str]:  # pragma: no cover
        """No-op: tests that exercise .cfg paths use the real Manager."""
        return None


def args_namespace(parameter=None, unq_style: Optional[str] = None) -> types.SimpleNamespace:
    """Return a ``SimpleNamespace(args=SimpleNamespace(...))`` shim suitable
    as the ``manager`` argument to :class:`genesispy.config_handler.ConfigHandler`."""
    args = types.SimpleNamespace(parameter=list(parameter or []), unq_style=unq_style)
    return types.SimpleNamespace(args=args)


def make_cfg_manager(parameter_specs=()) -> "StubManager":
    """Return a :class:`StubManager` whose ``cfg_handler`` is a real
    :class:`genesispy.config_handler.ConfigHandler` driven by
    ``parameter_specs``. Used by tests that need hierarchical CLI-override
    semantics without a full :class:`genesispy.manager.Manager`."""
    from genesispy.config_handler import ConfigHandler

    bare = args_namespace(parameter=parameter_specs)
    cfg = ConfigHandler(bare)
    mgr = StubManager(cfg_handler=cfg)
    mgr.args = bare.args
    return mgr
