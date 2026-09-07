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
import os
import pprint
import re
import sys
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Iterable, Optional

from . import reporting, json_io
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


# Human-readable source names for a resolved parameter's stored priority.
# Keyed by int rather than by the enum because define_param stores a bare
# ``flags.get("priority", 0)``: an untouched default is 0, not DECLARATION.
# No label contains '=', which keeps rendered footer lines from matching the
# ``// NAME = value`` banner shape that tests/_parity_normalize.py scans for.
PRIORITY_LABELS: dict[int, str] = {
    0:                                 "declaration default",
    int(Priority.DECLARATION):         "declaration default",
    int(Priority.EXTERNAL_CONFIG):     "config script (--cfg / configure)",
    int(Priority.EXTERNAL_PARAM_FILE): "config file (--json-cfg)",
    int(Priority.CMD_LINE):            "command line (--parameter)",
    int(Priority.INHERITANCE):         "parent instantiation",
    int(Priority.IMMUTABLE):           "forced (force_param)",
}


def priority_label(priority: Optional[int]) -> str:
    """Return the configuration source that wrote a parameter's ``priority``."""
    if priority is None:
        return "unknown"
    p = int(priority)
    label = PRIORITY_LABELS.get(p)
    if label is not None:
        return label
    # configure(..., priority=N) accepts any integer: name the nearest rung
    # at or below N and keep the raw number visible.
    rung = max((k for k in PRIORITY_LABELS if k <= p), default=0)
    return f"{PRIORITY_LABELS[rung]} (priority {p})"


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
        raise reporting.ParameterError(
            f"Malformed -parameter spec '{spec}': expected NAME=VALUE"
        )
    lhs, _, val = spec.partition("=")
    lhs = lhs.strip()
    if ":" in lhs:
        # Perl supports NAME:TYPE=VAL; not yet ported. Reject explicitly
        # rather than silently strip a trailing ':'.
        raise reporting.ParameterError(
            f"Malformed -parameter spec '{spec}': "
            "colon not allowed in parameter spec "
            "(':TYPE' annotations not supported)"
        )
    if not lhs:
        raise reporting.ParameterError(
            f"Malformed -parameter spec '{spec}': empty name"
        )
    segs, leaf = _split_dotted_name(lhs)
    if segs is None and "." in lhs:
        raise reporting.ParameterError(
            f"Malformed -parameter spec '{spec}': empty path segment or empty name"
        )
    return segs, leaf, _coerce_scalar(val)


def _unwrap_array(node: Any) -> list:
    """Convert a JSON-native ``__ArrayType__`` value to a Python list.

    Recurses into plain lists and dicts, coercing scalar leaves.  A dict
    value that itself carries a sentinel key (``__ArrayType__``,
    ``__HashType__``, ``__Val__``) is NOT unwrapped -- the sentinel key
    passes through untouched."""
    if isinstance(node, list):
        return [_normalise_value(v) for v in node]
    if not isinstance(node, dict):
        return [node] if node is not None else []
    return []


def _unwrap_hash(node: Any) -> dict:
    """Convert a JSON-native ``__HashType__`` value to a Python dict.

    Recurses into plain lists and dicts, coercing scalar leaves.  A dict
    value that itself carries a sentinel key is NOT unwrapped -- the
    sentinel key passes through untouched."""
    if not isinstance(node, dict):
        return {}
    return {k: _normalise_value(v) for k, v in node.items()}


def _normalise_value(v: Any) -> Any:
    """Normalise a JSON-native value.

    Recurses into plain lists and dicts; scalar leaves keep their JSON type
    (a string that spells a number stays a string, as XML::Simple gave
    Genesis2 the text).  Sentinel
    keys (``__ArrayType__``, ``__HashType__``, ``__Val__``) inside a nested
    dict are NOT detected -- they pass through with the key preserved.
    In practice this is harmless: ``genesispy-xml2json`` unwraps all nesting
    at conversion time, so tool-produced configs never contain nested
    wrappers; only hand-crafted JSON can trigger this."""
    if isinstance(v, list):
        return [_normalise_value(x) for x in v]
    if isinstance(v, dict):
        return {k: _normalise_value(x) for k, x in v.items()}
    return v


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


_DOTTED_NAME_RE = re.compile(r"(\w+\.)+\w+")


def _require_dotted(method: str, name: Any) -> tuple[tuple[str, ...], str]:
    """The ``.cfg`` API takes ``path.name`` (ConfigHandler.pm:1349-1356):
    at least one ``\\w+`` path segment before the parameter name."""
    if not isinstance(name, str) or not _DOTTED_NAME_RE.fullmatch(name):
        raise reporting.ConfigError(
            f"{method}: Expected first argument structure to have both path and "
            f"param name separated by a dot. Example: 'top.dut.subinst.prmname'. "
            f"Found: '{name}'"
        )
    head, _, leaf = name.rpartition(".")
    return tuple(head.split(".")), leaf


# Keys that may carry a parameter's value. ``__Val__`` is the JSON-native
# spelling; ``Val`` is what ``--json-out`` writes (Perl's WriteXml schema), so
# a snapshot can be fed back through ``--json-cfg``. ``InstancePath`` (Perl's
# pointer-to-instance form) is accepted by the validator but has no value
# here: such a parameter reads as absent.
_PARAM_VALUE_KEYS = ("__Val__", "Val", "__ArrayType__", "__HashType__", "InstancePath")

# Sentinel returned by _find_param when no matching Parameter exists.
# A separate sentinel lets callers tell "absent" apart from "explicitly
# set to JSON null", which the priority resolution in get_configuration
# previously collapsed.
_MISSING: Any = object()


def _root_node(db: Any) -> Optional[dict]:
    """Return the ``HierarchyTop`` node of a loaded config tree (or the
    tree itself when it is already a node)."""
    if not isinstance(db, dict):
        return None
    root = db.get("HierarchyTop", db)
    return root if isinstance(root, dict) else None


def _node_params(node: dict) -> list:
    items = node.get("Parameters")
    return items if isinstance(items, list) else []


def _node_subinstances(node: dict) -> list:
    items = node.get("SubInstances")
    return items if isinstance(items, list) else []


def _param_value(item: dict) -> Any:
    if "__Val__" in item:
        return _normalise_value(item["__Val__"])
    if "Val" in item:
        return _normalise_value(item["Val"])
    if "__ArrayType__" in item:
        return _unwrap_array(item["__ArrayType__"])
    if "__HashType__" in item:
        return _unwrap_hash(item["__HashType__"])
    return _MISSING


def _find_node(db: Any, instance_path: Optional[tuple[str, ...]]) -> Optional[dict]:
    """Return the node for ``instance_path`` (root..self), or None.

    Port of Perl ``find_xml_node`` (ConfigHandler.pm:812-868): the root's
    ``InstanceName`` must equal the first path segment, then each further
    segment selects a ``SubInstances`` entry by ``InstanceName``. With no
    path the root node itself is returned.
    """
    root = _root_node(db)
    if root is None:
        return None
    if instance_path is None:
        return root
    top_name = root.get("InstanceName")
    if top_name is None:
        return None
    if top_name != instance_path[0]:
        raise reporting.ConfigError(
            f"JSON config: unexpected top-level InstanceName {top_name!r}; "
            f"expected {instance_path[0]!r}"
        )
    node = root
    for token in instance_path[1:]:
        node = next(
            (s for s in _node_subinstances(node)
             if isinstance(s, dict) and s.get("InstanceName") == token),
            None,
        )
        if node is None:
            return None
    return node


def _find_param(
    db: Any, name: str, instance_path: Optional[tuple[str, ...]] = None
) -> Any:
    """Return the value of Parameter ``name`` on the node at
    ``instance_path`` (the root node when no path is given), or
    :data:`_MISSING`.

    Only that node's own ``Parameters`` list is read: a value written for
    one instance never applies to another, and ``ImmutableParameters`` is
    writeback-only metadata (Genesis2 ConfigHandler.pm:875-919).
    """
    node = _find_node(db, instance_path)
    if node is None:
        return _MISSING
    for item in _node_params(node):
        if isinstance(item, dict) and item.get("Name") == name:
            return _param_value(item)
    return _MISSING


def _validate_param_db(db: Any, path: str) -> None:
    """Reject a config tree that does not have the ``HierarchyTop`` shape.

    Mirrors the checks Perl makes while reading (ConfigHandler.pm:833-914):
    a single ``HierarchyTop`` root; ``Parameters`` a list of objects each
    with a non-empty ``Name`` and exactly one value key; no duplicate
    names on one node; ``SubInstances`` a list of objects each with an
    ``InstanceName``. ``""`` stands for an empty list (what
    ``genesispy-xml2json`` emits for an empty element).
    """
    def fail(where: str, msg: str) -> None:
        raise reporting.ConfigError(f"{path}: {where}: {msg}")

    if not isinstance(db, dict) or set(db) != {"HierarchyTop"}:
        fail("root", "expected a single HierarchyTop object")

    def check_node(node: Any, where: str) -> None:
        if not isinstance(node, dict):
            fail(where, "expected an object")
        params = node.get("Parameters")
        if params is not None and params != "":
            if not isinstance(params, list):
                fail(where, "Parameters must be a list of "
                     "{Name, __Val__ | Val | __ArrayType__ | __HashType__} objects")
            seen: set = set()
            for i, item in enumerate(params):
                w = f"{where}.Parameters[{i}]"
                if not isinstance(item, dict):
                    fail(w, "expected an object")
                nm = item.get("Name")
                if not isinstance(nm, str) or not nm:
                    fail(w, "Name missing or not a non-empty string")
                keys = [k for k in _PARAM_VALUE_KEYS if k in item]
                if len(keys) != 1:
                    fail(w, f"parameter {nm!r} must carry exactly one of "
                         f"{', '.join(_PARAM_VALUE_KEYS)} (found {keys or 'none'})")
                if nm in seen:
                    fail(where, f"parameter {nm!r} defined more than once")
                seen.add(nm)
        subs = node.get("SubInstances")
        if subs is not None and subs != "":
            if not isinstance(subs, list):
                fail(where, "SubInstances must be a list of objects")
            for i, sub in enumerate(subs):
                w = f"{where}.SubInstances[{i}]"
                if not isinstance(sub, dict):
                    fail(w, "expected an object")
                iname = sub.get("InstanceName")
                if not isinstance(iname, str) or not iname:
                    fail(w, "InstanceName missing or not a non-empty string")
                check_node(sub, f"{where}.{iname}")

    check_node(db["HierarchyTop"], "HierarchyTop")


def _json_scoped_entries(db: Any) -> dict[tuple[tuple[str, ...], str], dict]:
    """``{(instance_path, name): entry}`` for every valued parameter a config
    tree defines, keyed the way the scoped override DBs are. Empty when the
    root carries no ``InstanceName`` (no path can then resolve)."""
    root = _root_node(db)
    if root is None or not isinstance(root.get("InstanceName"), str):
        return {}
    out: dict[tuple[tuple[str, ...], str], dict] = {}
    prio = int(Priority.EXTERNAL_PARAM_FILE)

    def walk(node: dict, path: tuple[str, ...]) -> None:
        for item in _node_params(node):
            if not isinstance(item, dict) or not isinstance(item.get("Name"), str):
                continue
            value = _param_value(item)
            if value is not _MISSING:
                out[(path, item["Name"])] = {"value": value, "priority": prio}
        for sub in _node_subinstances(node):
            if isinstance(sub, dict) and isinstance(sub.get("InstanceName"), str):
                walk(sub, path + (sub["InstanceName"],))

    walk(root, (root["InstanceName"],))
    return out


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
        # Bare ``--parameter NAME=VALUE``: applies at every instance path.
        self._cmdln_db: dict[str, dict] = {}
        # Hierarchical (instance_path, param_name) -> entry. Populated by
        # ``--parameter top.child.x=2`` and ``configure("top.child.x", v)``;
        # configure() takes the dotted form only (ConfigHandler.pm:1349).
        self._cmdln_scoped_db: dict[tuple[tuple[str, ...], str], dict] = {}
        self._cfg_scoped_db: dict[tuple[tuple[str, ...], str], dict] = {}
        # Overrides a lookup has consumed; report_unused() lists the rest.
        self._used: set[tuple] = set()

        # File names recorded for diagnostics.
        self._json_in_filenames: list[str] = []
        self._json_out_filename: Optional[str] = None
        self._cfg_in_filenames: list[str] = []

        # Module uniquification style. Read from manager.args.unq_style if
        # present, default 'numeric'. Mirrors Perl ConfigHandler.UnqStyle.
        self.unq_style: str = manager.args.unq_style or "numeric"
        if self.unq_style not in ("numeric", "param"):
            raise reporting.GenesisPyError(
                f"Invalid unq_style {self.unq_style!r}; expected 'numeric' or 'param'"
            )

        # Parse ``manager.args.parameter`` if present (list of NAME=VALUE).
        self._init_cmdln_from_manager()

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
                    raise reporting.ParameterError(
                        f"Duplicate command-line parameter override "
                        f"of {name!r}"
                    )
                self._cmdln_db[name] = entry
            else:
                key = (path, name)
                if key in self._cmdln_scoped_db:
                    dotted = ".".join(path) + "." + name
                    raise reporting.ParameterError(
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
            raise reporting.ConfigError(f"JSON config file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise reporting.ConfigError(
                f"malformed JSON in {path}: {exc.msg}",
                location=f"{path}:{exc.lineno}",
            ) from exc
        _validate_param_db(new_db, path)
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
            raise reporting.GenesisPyError(
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
            raise reporting.ConfigError(
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
            raise reporting.ConfigError(f".cfg config file not found: {path}")
        path = os.path.abspath(path)
        self._cfg_in_filenames.append(path)

        # Perl's .cfg sandbox (ConfigHandler.pm:244-258) injects:
        # configure, get_configuration, exists_configuration,
        # remove_configuration, include, print_configuration,
        # get_top_name, get_synthtop_path, error.
        # genesispy adds `warning` (asymmetric extension, kept for
        # `.vpy`/`.cfg` parity — see Cluster H).
        from . import user_config as _uc

        cfg_namespace: dict[str, Any] = {
            "__name__": "__genesispy_cfg__",
            "__file__": path,
            "__builtins__": builtins,
            "configure": self.configure,
            "get_configuration": self.get_configuration,
            "exists_configuration": self.exists_configuration,
            "remove_configuration": self.remove_configuration,
            "include": self._include_dispatch,
            "print_configuration": self.print_configuration,
            "get_top_name": _uc._get_top_name,
            "get_synthtop_path": _uc._get_synthtop_path,
            "error": reporting.error,
            "warning": reporting.warning,
        }

        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        code = compile(src, path, "exec")
        # Active manager context lets injected ``get_top_name`` and
        # ``get_synthtop_path`` reach back to the Manager. No UniqueModule
        # is under elaboration during `.cfg` reading, so the module slot
        # is None (context() accepts that).
        with _uc.context(self.manager, None):
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

    def _param_lookup(
        self, name: str, instance_path: Optional[tuple[str, ...]] = None
    ) -> Any:
        """Return the JSON-config-sourced value for ``name`` on the node at
        ``instance_path`` (the root when None), or :data:`_MISSING`.

        Internal helper used by :meth:`get_configuration` and
        :meth:`exists_configuration` to disambiguate explicit JSON null
        from absence.
        """
        if not self._param_db:
            return _MISSING
        return _find_param(self._param_db, name, instance_path)

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

    def cmdln_scoped_db_snapshot(
        self,
    ) -> dict[tuple[tuple[str, ...], str], dict]:
        """Shallow copy of the hierarchical (path, name) -> entry DB."""
        return dict(self._cmdln_scoped_db)

    def scoped_db_snapshot(self) -> dict[tuple[tuple[str, ...], str], dict]:
        """Every path-addressed value -- JSON parameters, ``configure()``
        paths and ``--parameter PATH.NAME`` -- merged in that priority
        order. Read-only view; feeds the dedup subtree signature (Perl
        ``BuildParamPathMaps``, ConfigHandler.pm:398-410)."""
        merged = _json_scoped_entries(self._param_db)
        merged.update(self._cfg_scoped_db)
        merged.update(self._cmdln_scoped_db)
        return merged

    def scoped_overrides_for(self, instance_path: tuple[str, ...]) -> dict[str, Any]:
        """``{name: value}`` of every scoped override addressed to exactly
        ``instance_path``; marks each as used."""
        out: dict[str, Any] = {}
        for tag, db in (("cfg_scoped", self._cfg_scoped_db),
                        ("cmdln_scoped", self._cmdln_scoped_db)):
            for (path, name), entry in db.items():
                if path == instance_path:
                    out[name] = entry["value"]
                    self._used.add((tag, path, name))
        # The instance never looks the name up itself once a scoped value is
        # applied, so a bare override of the same name counts as consumed
        # (outranked, not misspelled).
        for name in out:
            if name in self._cmdln_db:
                self._used.add(("cmdln", name))
        return out

    def report_unused(self) -> list[str]:
        """One message per command-line or ``.cfg`` override no lookup
        consumed (Perl ``Finalize``, ConfigHandler.pm:436-442, which dies;
        genesispy warns). JSON parameters are not checked, as in Perl."""
        def dotted(path: tuple[str, ...], name: str) -> str:
            return ".".join((*path, name))

        found: list[tuple[str, str]] = []
        for name in self._cmdln_db:
            if ("cmdln", name) not in self._used:
                found.append((name, "--parameter"))
        for (path, name) in self._cmdln_scoped_db:
            if ("cmdln_scoped", path, name) not in self._used:
                found.append((dotted(path, name), "--parameter"))
        for (path, name) in self._cfg_scoped_db:
            if ("cfg_scoped", path, name) not in self._used:
                found.append((dotted(path, name), "configure()"))
        return [f"override {spec} was never used ({src})" for spec, src in sorted(found)]

    # ------------------------------------------------------------------ #
    # configure / get_configuration / exists / remove                    #
    # ------------------------------------------------------------------ #
    def configure(self, name: str, value: object, **flags: Any) -> None:
        """Record a configuration value (called from .cfg scripts).

        ``name`` is ``path.name``: the instance path (its first segment the
        top's instance name) and the parameter name, rightmost dot splits
        (ConfigHandler.pm:1349-1376). Stored at :attr:`Priority.EXTERNAL_CONFIG`
        unless ``priority`` is passed in ``flags``. The optional ``type`` flag
        (``'bool'``, ``'int'``, ``'float'``, ``'str'``) coerces ``value``.
        """
        type_hint = flags.get("type")
        if type_hint is not None:
            value = _coerce_with_type(value, type_hint)

        prio = flags.get("priority", int(Priority.EXTERNAL_CONFIG))
        try:
            prio_int = int(prio)
        except (ValueError, TypeError) as exc:
            raise reporting.ParameterError(
                f"configure({name!r}, priority={prio!r}): "
                f"priority must be an integer (or Priority enum value)"
            ) from exc

        # Caller's filename for diagnostics (the .cfg being exec'd).
        source_file = sys._getframe(1).f_code.co_filename

        key = _require_dotted("configure", name)
        entry = {
            "value": value,
            "priority": prio_int,
            "source_file": source_file,
        }
        # Priority-aware write: a lower-priority second call to the same
        # name is a no-op; an equal-or-higher call overwrites and warns.
        existing = self._cfg_scoped_db.get(key)
        if existing is not None and prio_int < existing["priority"]:
            return
        if existing is not None:
            reporting.warning(
                f"configure: redefinition of '{name}' "
                f"(was set at {existing.get('source_file')!r}, "
                f"now at {source_file!r})"
            )
        self._cfg_scoped_db[key] = entry

    def _address(
        self, method: str, name: str, instance_path: Optional[tuple[str, ...]]
    ) -> tuple[tuple[str, ...], str]:
        """``(path, leaf)`` for a lookup: the dotted ``name`` alone (the
        ``.cfg`` API form), or a bare ``name`` at ``instance_path`` (the
        engine's form)."""
        if instance_path is None:
            return _require_dotted(method, name)
        return tuple(instance_path), name

    def get_configuration(
        self,
        name: str,
        *,
        instance_path: Optional[tuple[str, ...]] = None,
    ) -> Optional[object]:
        """Return the highest-priority value for a parameter across all
        sources; ``ConfigError`` when no source defines it
        (ConfigHandler.pm:1512).

        ``name`` is ``path.name``, or a bare name when ``instance_path``
        gives the path. Scoped overrides (``--parameter top.child.x=2``,
        ``configure("top.child.x", v)``) match by exact instance-path
        equality (ConfigHandler.pm:355-372), JSON ``Parameters`` are read
        from the node at that path only, and a bare ``--parameter`` applies
        at every path. A scoped command-line match wins outright.
        """
        path, leaf = self._address("get_configuration", name, instance_path)
        value, prio = self._get_configuration_with_priority(leaf, instance_path=path)
        if prio is None:
            raise reporting.ConfigError(
                f"get_configuration: Could not find parameter '{'.'.join((*path, leaf))}'"
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

        # Every source that names the parameter counts as consumed, even
        # when a higher-priority source outranks it: layering the same
        # parameter across sources is legitimate and must not warn.
        if instance_path is not None:
            scoped = self._cmdln_scoped_db.get((instance_path, name))
            cfg_scoped = self._cfg_scoped_db.get((instance_path, name))
            if scoped is not None:
                self._used.add(("cmdln_scoped", instance_path, name))
            if cfg_scoped is not None:
                self._used.add(("cfg_scoped", instance_path, name))
            if scoped is not None:
                return scoped["value"], int(scoped["priority"])
            if cfg_scoped is not None:
                candidates.append(
                    (cfg_scoped["priority"], cfg_scoped["value"])
                )

        cmd = self._cmdln_db.get(name)
        if cmd is not None:
            self._used.add(("cmdln", name))
            candidates.append((cmd["priority"], cmd["value"]))

        param_val = self._param_lookup(name, instance_path)
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
        """True iff some source defines the parameter; same addressing as
        :meth:`get_configuration`."""
        path, leaf = self._address("exists_configuration", name, instance_path)
        if (path, leaf) in self._cmdln_scoped_db or (path, leaf) in self._cfg_scoped_db:
            return True
        if leaf in self._cmdln_db:
            return True
        return self._param_lookup(leaf, path) is not _MISSING

    def remove_configuration(self, name: str) -> None:
        """Remove ``path.name`` from the ``.cfg`` database (JSON and command
        line untouched)."""
        key = _require_dotted("remove_configuration", name)
        if key in self._cfg_scoped_db:
            reporting.warning(
                f"remove_configuration: removing previously configured "
                f"'{name}' (was {self._cfg_scoped_db[key]['value']!r})"
            )
            del self._cfg_scoped_db[key]

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

    * ``"full"``  -- every param, declared defaults included: forced
      (``force=True`` / ``force_param``) ones under ImmutableParameters,
      the rest under Parameters; the full subinstance tree.
    * ``"small"`` -- Parameters and full subinstance tree; the
      ImmutableParameters bucket is dropped.
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
    return {"HierarchyTop": _stats_entry(top_inst, variant)}


def _instance_path_dotted(inst: Any) -> str:
    return ".".join(inst._instance_path_segments())


def _stats_entry(inst: Any, variant: str) -> dict:
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
    """Return ``(Parameters, ImmutableParameters)`` item lists.

    Perl splits by recursion (ConfigHandler.pm:683-708); genesispy puts
    force-pinned params (IMMUTABLE priority) in the second bucket, which
    only the ``full`` variant emits.
    """
    live: list[dict] = []
    immut: list[dict] = []
    ext_param = int(Priority.EXTERNAL_PARAM_FILE)
    immutable = int(Priority.IMMUTABLE)
    for name, p in params.items():
        prio = int(p.get("priority", 0))
        if variant == "tiny" and prio < ext_param:
            continue
        item: dict[str, Any] = {"Name": name, "Val": p.get("value")}
        doc = p.get("doc")
        if doc:
            item["Doc"] = doc
        if prio >= immutable and variant != "tiny":
            if variant == "full":
                immut.append(item)
            continue
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
