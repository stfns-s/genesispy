"""Genesis2 ConfigHandler ported from Perl.

Combines three configuration sources with a priority hierarchy:

* ``.cfg`` Python script configuration (lowest, ``EXTERNAL_CONFIG``)
* JSON parameter file (``EXTERNAL_PARAM_FILE``)
* command-line ``-parameter NAME=VAL`` overrides (highest)

Higher-priority sources override lower ones when
:meth:`ConfigHandler.get_configuration` is called.

XML support has been factored out to ``genesispy.tools.xml_json``; convert
legacy ``.xml`` configs to JSON via ``genesispy-xml2json`` before feeding
them to genesispy.
"""

from __future__ import annotations

import json

import builtins
import inspect
import os
import pprint
import runpy
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Iterable, Optional

from . import errors, json_io
from ._scalars import coerce_scalar as _coerce_scalar

if TYPE_CHECKING:  # pragma: no cover
    from .manager import Manager


class Priority(IntEnum):
    """Configuration priority ladder used by ``get_configuration``.

    Order matches Perl Genesis2: ``CMDLN > PARAM_FILE > CFG``
    (CMD_LINE=30, EXTERNAL_PARAM_FILE=20, EXTERNAL_CONFIG=10). Numerics are
    spaced by 10 to leave room for future tiers.
    """

    DECLARATION = 5
    EXTERNAL_CONFIG = 10    # values from read_cfg / configure()
    EXTERNAL_PARAM_FILE = 20  # values from read_json
    CMD_LINE = 30           # values from -parameter NAME=VAL
    INHERITANCE = 40        # parent-kwarg pass via override_param
    IMMUTABLE = 50          # force_param: pinned, top-of-ladder


def _coerce_with_type(value: Any, type_hint: Optional[str]) -> Any:
    """Coerce ``value`` according to ``flags['type']``."""
    if type_hint is None:
        return _coerce_scalar(value)
    t = type_hint.lower()
    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            low = value.strip().lower()
            if low in ("1", "true", "yes", "on"):
                return True
            if low in ("0", "false", "no", "off"):
                return False
        return bool(value)
    if t == "int":
        try:
            return int(value)
        except (ValueError, TypeError):
            return value
    if t == "float":
        try:
            return float(value)
        except (ValueError, TypeError):
            return value
    if t == "str":
        return str(value)
    return _coerce_scalar(value)


def _parse_cmdln_param(
    spec: str,
) -> tuple[Optional[tuple[str, ...]], str, Any]:
    """Parse ``"NAME=VALUE"`` or ``"PATH.NAME=VALUE"`` strings.

    Returns ``(path_segments_or_None, name, coerced_value)``. The
    rightmost ``.`` before ``=`` separates instance path from parameter
    name (Genesis2 ConfigHandler.pm:355-367). Flat specs like ``WIDTH=8``
    return ``(None, "WIDTH", 8)``.

    Raises :class:`ParameterError` on malformed input (missing ``=``,
    empty name, or empty path segment).
    """
    if "=" not in spec:
        raise errors.ParameterError(
            f"Malformed -parameter spec '{spec}': expected NAME=VALUE"
        )
    lhs, _, val = spec.partition("=")
    lhs = lhs.strip()
    if ":" in lhs:
        # Perl supports NAME:TYPE=VAL; not yet ported. Reject explicitly
        # rather than silently strip a trailing ':'.
        raise errors.ParameterError(
            f"Malformed -parameter spec '{spec}': "
            "colon not allowed in parameter spec "
            "(':TYPE' annotations not supported)"
        )
    if not lhs:
        raise errors.ParameterError(
            f"Malformed -parameter spec '{spec}': empty name"
        )
    segs, leaf = _split_dotted_name(lhs)
    if segs is None and "." in lhs:
        raise errors.ParameterError(
            f"Malformed -parameter spec '{spec}': empty path segment or empty name"
        )
    return segs, leaf, _coerce_scalar(val)


def _unwrap_array(node: Any) -> list:
    """Convert a JSON-native ``__ArrayType__`` value to a Python list,
    recursively normalising nested wrapped children."""
    if isinstance(node, list):
        return [_normalise_value(v) for v in node]
    if not isinstance(node, dict):
        return [node] if node is not None else []
    return []


def _unwrap_hash(node: Any) -> dict:
    """Convert a JSON-native ``__HashType__`` value to a Python dict,
    recursively normalising nested wrapped children."""
    if not isinstance(node, dict):
        return {}
    return {k: _normalise_value(v) for k, v in node.items()}


def _normalise_value(v: Any) -> Any:
    """Normalise a JSON-native value, recursing into nested wrappers."""
    if isinstance(v, list):
        return [_normalise_value(x) for x in v]
    if isinstance(v, dict):
        return {k: _normalise_value(x) for k, x in v.items()}
    return _coerce_scalar(v)


def _split_dotted_name(name: str) -> tuple[Optional[tuple[str, ...]], str]:
    """Split a dotted parameter name into ``(segments, leaf)``.

    Returns ``(None, name)`` when the name has no dots, or when the dotted
    form is malformed (empty leaf or empty path segment). Callers that
    need to distinguish "flat" from "malformed" can re-check ``"." in
    name``.
    """
    if "." not in name:
        return None, name
    head, _, leaf = name.rpartition(".")
    segs = tuple(head.split("."))
    if not leaf or not all(segs):
        return None, name
    return segs, leaf


_PARAM_VALUE_KEYS = frozenset(
    {"__Val__", "__ArrayType__", "__HashType__"}
)

# Sentinel returned by _find_param when no matching Parameter exists.
# A separate sentinel lets callers tell "absent" apart from "explicitly
# set to JSON null", which the priority resolution in get_configuration
# previously collapsed.
_MISSING: Any = object()


def _find_param(node: Any, name: str) -> Any:
    """Recursively search the JSON-native db tree for a Parameter element
    with ``Name == name`` and return its value (``__Val__`` /
    ``__ArrayType__`` / ``__HashType__``). Returns :data:`_MISSING` when
    no match is found or the Parameter has no value-bearing key.

    Recursion skips the value-bearing keys so user data inside a
    ``__HashType__`` cannot accidentally shadow a real parameter via a
    stray ``Name`` key.
    """
    if isinstance(node, dict):
        nm = node.get("Name")
        if isinstance(nm, str) and nm == name:
            if "__Val__" in node:
                return _normalise_value(node["__Val__"])
            if "__ArrayType__" in node:
                return _unwrap_array(node["__ArrayType__"])
            if "__HashType__" in node:
                return _unwrap_hash(node["__HashType__"])
            return _MISSING
        for k, v in node.items():
            if k in _PARAM_VALUE_KEYS:
                continue
            r = _find_param(v, name)
            if r is not _MISSING:
                return r
    elif isinstance(node, list):
        for v in node:
            r = _find_param(v, name)
            if r is not _MISSING:
                return r
    return _MISSING


def _deep_merge(dst: dict, src: dict) -> dict:
    """Recursively merge ``src`` into ``dst`` in place, returning ``dst``.

    Dicts merge key-by-key; matching list values concatenate; everything
    else in ``src`` overwrites ``dst``. Used by ConfigHandler.read_json
    (also reachable via ``include('foo.json')`` from a ``.cfg``) so a
    sequence of include() calls accumulates into the same `_param_db`
    rather than clobbering prior reads.
    """
    for k, v in src.items():
        if k in dst and isinstance(dst[k], dict) and isinstance(v, dict):
            _deep_merge(dst[k], v)
        elif k in dst and isinstance(dst[k], list) and isinstance(v, list):
            dst[k] = dst[k] + v
        else:
            dst[k] = v
    return dst


class ConfigHandler:
    """Holds XML, .cfg and command-line configuration.

    See ``Genesis2/PerlLibs/Genesis2/ConfigHandler.pm`` for the
    behavioural reference.
    """

    def __init__(self, manager: "Manager") -> None:
        self.manager = manager
        self.debug = 0

        # Backing stores.
        self._param_db: dict = {}
        self._cfg_db: dict[str, dict] = {}
        self._cmdln_db: dict[str, dict] = {}
        # Hierarchical (instance_path, param_name) -> entry. Populated by
        # ``--parameter top.child.x=2`` and ``configure("top.child.x", v)``.
        self._cmdln_scoped_db: dict[tuple[tuple[str, ...], str], dict] = {}
        self._cfg_scoped_db: dict[tuple[tuple[str, ...], str], dict] = {}

        # File names recorded for diagnostics.
        self._json_in_filenames: list[str] = []
        self._json_out_filename: Optional[str] = None
        self._cfg_in_filenames: list[str] = []

        # Module uniquification style. Read from manager.args.unq_style if
        # present, default 'numeric'. Mirrors Perl ConfigHandler.UnqStyle.
        self.unq_style: str = manager.args.unq_style or "numeric"
        self._validate_unq_style(self.unq_style)

        # Parse ``manager.args.parameter`` if present (list of NAME=VALUE).
        self._init_cmdln_from_manager()

    @staticmethod
    def _validate_unq_style(style: str) -> None:
        if style not in ("numeric", "param"):
            raise errors.GenesisPyError(
                f"Invalid unq_style {style!r}; expected 'numeric' or 'param'"
            )

    def set_unq_style(self, style: str) -> None:
        """Set the module uniquification style (mirrors Perl SetUnqStyle)."""
        self._validate_unq_style(style)
        self.unq_style = style

    # ------------------------------------------------------------------ #
    # Cmd-line parameter ingestion                                       #
    # ------------------------------------------------------------------ #
    def _init_cmdln_from_manager(self) -> None:
        params: Optional[Iterable[str]] = self.manager.args.parameter
        if not params:
            return
        for spec in params:
            path, name, val = _parse_cmdln_param(spec)
            entry = {
                "value": val,
                "priority": int(Priority.CMD_LINE),
                "source_file": "<command-line>",
            }
            if path is None:
                if name in self._cmdln_db:
                    raise errors.ParameterError(
                        f"Duplicate command-line parameter override "
                        f"of {name!r}"
                    )
                self._cmdln_db[name] = entry
            else:
                key = (path, name)
                if key in self._cmdln_scoped_db:
                    dotted = ".".join(path) + "." + name
                    raise errors.ParameterError(
                        f"Duplicate command-line parameter override "
                        f"of {dotted!r}"
                    )
                self._cmdln_scoped_db[key] = entry

    # ------------------------------------------------------------------ #
    # JSON I/O                                                           #
    # ------------------------------------------------------------------ #
    def read_json(self, path: str) -> None:
        """Read a JSON config file and merge it into the in-memory database.

        Repeated calls deep-merge into ``_param_db`` (matching dicts merge
        key-by-key; matching lists concatenate).
        """
        try:
            new_db = json_io.read_json(path)
        except FileNotFoundError as exc:
            raise errors.ConfigError(f"JSON config file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise errors.ConfigError(
                f"malformed JSON in {path}: {exc.msg}",
                location=f"{path}:{exc.lineno}",
            ) from exc
        self._json_in_filenames.append(path)
        if not self._param_db:
            self._param_db = new_db
        else:
            _deep_merge(self._param_db, new_db)

    def write_json(self, path: str, top_inst: Any = None) -> None:
        """Serialise the elaborated module tree at ``top_inst`` as a
        ``HierarchyTop`` snapshot (Perl ``ConfigHandler.pm::WriteXml`` /
        ``extract_stats`` port).

        Writes three sibling files in the directory of ``path``. Given
        ``path = "<dir>/<stem><ext>"``:

        * ``<dir>/<stem><ext>``           -- full snapshot
        * ``<dir>/<stem>-small<ext>``     -- omits ``ImmutableParameters``
        * ``<dir>/<stem>-tiny<ext>``      -- only user-overridden params
                                             (priority >= EXTERNAL_PARAM_FILE)

        ``top_inst`` is required (``Manager._top_inst`` after
        :meth:`Manager.gen_verilog`). Passing ``None`` raises
        :class:`GenesisPyError`; ``--json-out`` outside an elaborated flow
        is unsupported.
        """
        if top_inst is None:
            raise errors.GenesisPyError(
                "--json-out requires an elaborated module tree; "
                "run gen_verilog first"
            )
        self._json_out_filename = path
        directory = os.path.dirname(path)
        stem, ext = os.path.splitext(os.path.basename(path))
        for variant, fname in (
            ("full", path),
            ("small", os.path.join(directory, f"{stem}-small{ext}")),
            ("tiny", os.path.join(directory, f"{stem}-tiny{ext}")),
        ):
            tree = extract_stats(top_inst, variant=variant)
            json_io.write_json(tree, fname)

    # ------------------------------------------------------------------ #
    # .cfg script execution                                              #
    # ------------------------------------------------------------------ #
    def _include_dispatch(self, path: str) -> None:
        """Dispatch ``include(path)`` from a .cfg sandbox by extension.

        ``.json`` -> :meth:`read_json`, anything else (including ``.cfg``
        and extension-less paths) -> :meth:`read_cfg`. Extension
        comparison is case-insensitive. Legacy ``.xml`` inputs must be
        converted to JSON via ``genesispy-xml2json`` first.
        """
        resolved = self.manager._resolve_cfg_path(path) or path
        ext = os.path.splitext(resolved)[1].lower()
        if ext == ".xml":
            raise errors.ConfigError(
                f"include({path!r}): XML config files are no longer "
                "accepted; convert with genesispy-xml2json first"
            )
        if ext == ".json":
            self.read_json(resolved)
        else:
            self.read_cfg(resolved)

    def read_cfg(self, path: str) -> None:
        """Execute a Python ``.cfg`` script in a Genesis-flavoured namespace.

        The script may call ``configure(name, value)``,
        ``get_configuration(name)``, ``exists_configuration(name)``,
        ``include(other_path)`` and ``error(msg)``. The full standard
        library is also available — the namespace is *not* sandboxed
        (full ``__builtins__`` exposed deliberately, mirroring Perl
        ``do FILE`` semantics).

        Trusted-input only: the file is exec'd with ``runpy``-style
        semantics. Do NOT pass untrusted ``.cfg`` paths.
        """
        if not os.path.isfile(path):
            raise errors.ConfigError(f".cfg config file not found: {path}")
        path = os.path.abspath(path)
        self._cfg_in_filenames.append(path)

        cfg_namespace: dict[str, Any] = {
            "__name__": "__genesispy_cfg__",
            "__file__": path,
            "__builtins__": builtins,
            "configure": self.configure,
            "get_configuration": self.get_configuration,
            "exists_configuration": self.exists_configuration,
            "remove_configuration": self.remove_configuration,
            "include": self._include_dispatch,
            "error": errors.error,
            "warning": errors.warning,
        }

        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        code = compile(src, path, "exec")
        exec(code, cfg_namespace)

    # ------------------------------------------------------------------ #
    # Per-source value lookup                                            #
    # ------------------------------------------------------------------ #
    def get_param_val(self, name: str) -> Optional[object]:
        """Return the JSON-config-sourced value for ``name``, or None.

        Legacy name: the underlying store is now JSON-only. A returned
        ``None`` may mean either "not found" or "found and explicitly
        null" -- callers that need to distinguish should use
        :meth:`_param_lookup` (sentinel-aware) or
        :meth:`exists_configuration`.
        """
        val = self._param_lookup(name)
        return None if val is _MISSING else val

    def _param_lookup(self, name: str) -> Any:
        """Return the JSON-config-sourced value for ``name``, or
        :data:`_MISSING`.

        Internal helper used by :meth:`get_configuration` and
        :meth:`exists_configuration` to disambiguate explicit JSON null
        from absence.
        """
        if not self._param_db:
            return _MISSING
        return _find_param(self._param_db, name)

    def get_cfg_param_val(self, name: str) -> Optional[object]:
        """Return the .cfg-sourced value for ``name``, or None."""
        rec = self._cfg_db.get(name)
        if rec is None:
            return None
        return rec.get("value")

    def get_cmdln_param_val(self, name: str) -> Optional[object]:
        """Return the command-line-sourced value for ``name``, or None."""
        rec = self._cmdln_db.get(name)
        if rec is None:
            return None
        return rec.get("value")

    def cmdln_db_snapshot(self) -> dict[str, dict]:
        """Shallow copy of the flat command-line override DB.

        Read-only view for tests and diagnostics; modifying the returned
        dict does not affect the ConfigHandler.
        """
        return dict(self._cmdln_db)

    def cfg_db_snapshot(self) -> dict[str, dict]:
        """Shallow copy of the .cfg-sourced override DB."""
        return dict(self._cfg_db)

    def cmdln_scoped_db_snapshot(
        self,
    ) -> dict[tuple[tuple[str, ...], str], dict]:
        """Shallow copy of the hierarchical (path, name) -> entry DB."""
        return dict(self._cmdln_scoped_db)

    # ------------------------------------------------------------------ #
    # configure / get_configuration / exists / remove                    #
    # ------------------------------------------------------------------ #
    def configure(self, name: str, value: object, **flags: Any) -> None:
        """Record a configuration value (called from .cfg scripts).

        Stored at :attr:`Priority.EXTERNAL_CONFIG` unless ``priority`` is
        passed in ``flags``. The optional ``type`` flag (``'bool'``,
        ``'int'``, ``'float'``, ``'str'``) coerces ``value`` accordingly.

        A dotted ``name`` like ``"top.child.x"`` is parsed into an
        instance path and parameter name (rightmost ``.`` splits) and
        recorded in the scoped DB so ``get_configuration("x",
        instance_path=("top","child"))`` can find it. Mirrors the
        hierarchical CLI override path (Perl ConfigHandler.pm:1349-1376).
        """
        type_hint = flags.get("type")
        if type_hint is not None:
            value = _coerce_with_type(value, type_hint)

        prio = flags.get("priority", int(Priority.EXTERNAL_CONFIG))
        try:
            prio_int = int(prio)
        except (ValueError, TypeError) as exc:
            raise errors.ParameterError(
                f"configure({name!r}, priority={prio!r}): "
                f"priority must be an integer (or Priority enum value)"
            ) from exc

        # Find caller filename for diagnostics.
        source_file = "<unknown>"
        try:
            frame = inspect.stack()[1]
            source_file = frame.filename
        except Exception:  # pragma: no cover
            pass

        path_segs, leaf = _split_dotted_name(name)

        entry = {
            "value": value,
            "priority": prio_int,
            "source_file": source_file,
        }

        # Priority-aware write: a lower-priority second call to the same
        # name is a no-op; an equal-or-higher call overwrites and warns.
        if path_segs is not None:
            key = (path_segs, leaf)
            existing = self._cfg_scoped_db.get(key)
            if existing is not None and prio_int < existing["priority"]:
                return
            if existing is not None:
                errors.warning(
                    f"configure: redefinition of '{name}' "
                    f"(was set at {existing.get('source_file')!r}, "
                    f"now at {source_file!r})"
                )
            self._cfg_scoped_db[key] = entry
            return

        existing = self._cfg_db.get(leaf)
        if existing is not None and prio_int < existing["priority"]:
            return
        if existing is not None:
            errors.warning(
                f"configure: redefinition of '{leaf}' "
                f"(was set at {existing.get('source_file')!r}, "
                f"now at {source_file!r})"
            )
        self._cfg_db[leaf] = entry

    def get_configuration(
        self,
        name: str,
        *,
        instance_path: Optional[tuple[str, ...]] = None,
    ) -> Optional[object]:
        """Return the highest-priority value for ``name`` across all
        sources, or None.

        When ``instance_path`` is provided, hierarchical CLI overrides
        like ``--parameter top.child.x=2`` are matched first by **exact**
        instance-path equality (Genesis2 ConfigHandler.pm:355-372). A
        scoped match wins over flat sources at the same priority.
        """
        value, _prio = self._get_configuration_with_priority(
            name, instance_path=instance_path
        )
        return value

    def get_configuration_with_priority(
        self,
        name: str,
        *,
        instance_path: Optional[tuple[str, ...]] = None,
    ) -> tuple[Optional[object], Optional[int]]:
        """Like :meth:`get_configuration` but also returns the priority
        of the winning source. Returns ``(None, None)`` when no source
        defines ``name``.
        """
        return self._get_configuration_with_priority(
            name, instance_path=instance_path
        )

    def _get_configuration_with_priority(
        self,
        name: str,
        *,
        instance_path: Optional[tuple[str, ...]] = None,
    ) -> tuple[Optional[object], Optional[int]]:
        candidates: list[tuple[int, object]] = []

        if instance_path is not None:
            scoped = self._cmdln_scoped_db.get((instance_path, name))
            if scoped is not None:
                return scoped["value"], int(scoped["priority"])
            cfg_scoped = self._cfg_scoped_db.get((instance_path, name))
            if cfg_scoped is not None:
                candidates.append(
                    (cfg_scoped["priority"], cfg_scoped["value"])
                )

        cmd = self._cmdln_db.get(name)
        if cmd is not None:
            candidates.append((cmd["priority"], cmd["value"]))

        cfg = self._cfg_db.get(name)
        if cfg is not None:
            candidates.append((cfg["priority"], cfg["value"]))

        param_val = self._param_lookup(name)
        if param_val is not _MISSING:
            candidates.append((int(Priority.EXTERNAL_PARAM_FILE), param_val))

        if not candidates:
            return None, None
        candidates.sort(key=lambda t: t[0], reverse=True)
        prio, value = candidates[0]
        return value, int(prio)

    def exists_configuration(
        self,
        name: str,
        *,
        instance_path: Optional[tuple[str, ...]] = None,
    ) -> bool:
        """True iff some source defines ``name``.

        When ``instance_path`` is provided, a hierarchical CLI override
        scoped to that exact path also counts.
        """
        if instance_path is not None:
            if (instance_path, name) in self._cmdln_scoped_db:
                return True
            if (instance_path, name) in self._cfg_scoped_db:
                return True
        if name in self._cmdln_db or name in self._cfg_db:
            return True
        return self._param_lookup(name) is not _MISSING

    def remove_configuration(self, name: str) -> None:
        """Remove ``name`` from the .cfg database (XML and cmdln untouched).

        A dotted ``name`` removes the matching path-scoped entry (if any).
        """
        segs, leaf = _split_dotted_name(name)
        if segs is not None:
            key = (segs, leaf)
            if key in self._cfg_scoped_db:
                errors.warning(
                    f"remove_configuration: removing previously "
                    f"configured '{name}' (was "
                    f"{self._cfg_scoped_db[key]['value']!r})"
                )
                del self._cfg_scoped_db[key]
                return
        if name in self._cfg_db:
            errors.warning(
                f"remove_configuration: removing previously configured "
                f"'{name}' (was {self._cfg_db[name]['value']!r})"
            )
            del self._cfg_db[name]

    # ------------------------------------------------------------------ #
    # Pretty printing                                                    #
    # ------------------------------------------------------------------ #
    def print_configuration(self) -> str:
        """Return a Data::Dumper-style summary of all configuration."""
        out: list[str] = []
        out.append("=== Genesis2 ConfigHandler dump ===")
        out.append(f"  JSON in:  {self._json_in_filenames}")
        out.append(f"  JSON out: {self._json_out_filename}")
        out.append(f"  CFG in:   {self._cfg_in_filenames}")
        out.append("")
        out.append("--- Command-line (priority CMD_LINE) ---")
        if self._cmdln_db:
            out.append(pprint.pformat(self._cmdln_db, width=100))
        else:
            out.append("  (empty)")
        out.append("")
        out.append("--- JSON (priority EXTERNAL_PARAM_FILE) ---")
        if self._param_db:
            out.append(pprint.pformat(self._param_db, width=100))
        else:
            out.append("  (empty)")
        out.append("")
        out.append("--- .cfg (priority EXTERNAL_CONFIG) ---")
        if self._cfg_db:
            out.append(pprint.pformat(self._cfg_db, width=100))
        else:
            out.append("  (empty)")
        out.append("")
        out.append("--- .cfg scoped (priority EXTERNAL_CONFIG) ---")
        if self._cfg_scoped_db:
            out.append(pprint.pformat(self._cfg_scoped_db, width=100))
        else:
            out.append("  (empty)")
        return "\n".join(out)


# ---------------------------------------------------------------------- #
# Hierarchy snapshot (Perl ConfigHandler.pm::extract_stats port)         #
# ---------------------------------------------------------------------- #

def extract_stats(top_inst: Any, *, variant: str = "full") -> dict:
    """Walk the elaborated tree at ``top_inst`` and return a JSON-native
    ``HierarchyTop`` snapshot.

    ``variant`` selects the Perl output flavour:

    * ``"full"``  -- every live param (Parameters bucket) plus
      ImmutableParameters and the full subinstance tree.
    * ``"small"`` -- Parameters and full subinstance tree; no
      ImmutableParameters.
    * ``"tiny"``  -- only Parameters with priority >= EXTERNAL_PARAM_FILE
      (JSON, CLI, parent-kwargs, and force-pinned overrides;
      ``.cfg`` ``configure(...)`` overrides at ``EXTERNAL_CONFIG`` are
      excluded by design — mirrors Perl
      ``ConfigHandler.pm::extract_stats``); subinstances with no
      relevant params and no relevant descendants are pruned.

    Schema mirrors the Perl ``ConfigHandler.pm::extract_stats`` output
    after ``genesispy-xml2json`` post-processing: the ``HierarchyTop``
    element directly carries the root instance fields (InstanceName,
    BaseModuleName, UniqueModuleName, Parameters, ImmutableParameters,
    SubInstances). ``Parameters`` / ``ImmutableParameters`` /
    ``SubInstances`` are bare lists of dicts (xml2json collapses the
    ``ParameterItem`` / ``SubInstanceItem`` wrappers; we emit the same
    collapsed form). Clones emit a single ``CloneOf.InstancePath``
    (Perl ConfigHandler.pm:673) with no params or subinstances.
    Instance paths use ``.`` separators. Synonyms appear as sibling
    entries inside the parent's ``SubInstances`` list with
    ``SynonymFor`` set to the primary instance path.
    """
    if variant not in ("full", "small", "tiny"):
        raise ValueError(f"extract_stats: unknown variant {variant!r}")
    return {"HierarchyTop": _stats_entry(top_inst, variant, root=True)}


def _instance_path_dotted(inst: Any) -> str:
    return ".".join(inst._instance_path_segments())


def _stats_entry(inst: Any, variant: str, *, root: bool = False) -> dict:
    entry: dict[str, Any] = {
        "InstanceName": inst.get_instance_name(),
        "UniqueModuleName": inst._unique_module_name,
        "BaseModuleName": type(inst).__name__,
    }
    clone_of = inst._clone_of
    if clone_of is not None:
        entry["CloneOf"] = {"InstancePath": _instance_path_dotted(clone_of)}
        return entry

    live, immut = _split_params(inst._params, variant)
    if live:
        entry["Parameters"] = live
    if variant == "full" and immut:
        entry["ImmutableParameters"] = immut

    sub_entries: list[dict] = []
    for child in inst._sub_instances.values():
        child_entry = _stats_entry(child, variant)
        if variant == "tiny" and not _has_content(child_entry):
            continue
        sub_entries.append(child_entry)
        sub_entries.extend(_synonym_stubs(child))
    if sub_entries:
        entry["SubInstances"] = sub_entries
    return entry


def _split_params(
    params: dict, variant: str
) -> tuple[list[dict], list[dict]]:
    # Perl splits live/immut by recursion (ConfigHandler.pm:683-708), not
    # priority. No recursion-tracking here, so immut is always empty.
    live: list[dict] = []
    immut: list[dict] = []
    decl = int(Priority.DECLARATION)
    ext_param = int(Priority.EXTERNAL_PARAM_FILE)
    for name, p in params.items():
        prio = int(p.get("priority", 0))
        state = p.get("state")
        # NeverUsed filter: declared but never read/overridden.
        if prio <= decl and state == "DEFINED":
            continue
        if variant == "tiny" and prio < ext_param:
            continue
        item: dict[str, Any] = {"Name": name, "Val": p.get("value")}
        doc = p.get("doc")
        if doc:
            item["Doc"] = doc
        live.append(item)
    return live, immut


def _synonym_stubs(inst: Any) -> list[dict]:
    stubs: list[dict] = []
    for syn_name in inst.get_synonyms():
        stubs.append({
            "InstanceName": syn_name,
            "UniqueModuleName": inst._unique_module_name,
            "BaseModuleName": type(inst).__name__,
            "SynonymFor": _instance_path_dotted(inst),
        })
    return stubs


def _has_content(entry: dict) -> bool:
    """Tiny-variant pruning predicate: keep an entry only if it carries
    a CloneOf reference, any Parameters, or any retained children."""
    if "CloneOf" in entry:
        return True
    if entry.get("Parameters"):
        return True
    return bool(entry.get("SubInstances"))
