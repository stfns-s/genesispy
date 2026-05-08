"""XML <-> JSON translator for Genesis2-style configuration trees.

The genesispy core deals with JSON only. This helper exists for users
with legacy Genesis2 XML configs: convert once, run genesispy on the
JSON output. The reverse direction (JSON -> XML) is provided for
symmetry and debugging.

Two CLI entry points:

  * ``genesispy-xml2json IN.xml OUT.json``
  * ``genesispy-json2xml IN.json OUT.xml``

Library API: :func:`xml_to_json` and :func:`json_to_xml`.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Iterable, Optional

try:
    from lxml import etree as _ET  # type: ignore
    _USING_LXML = True
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as _ET  # type: ignore
    _USING_LXML = False

from .._scalars import coerce_scalar as _coerce_scalar_str


# Tags that always become lists when reading XML (matches XML::Simple's
# ForceArray idiom in the original Genesis2 codebase).
DEFAULT_FORCE_LIST: frozenset[str] = frozenset(
    {
        "Parameter",
        "ParameterItem",
        "ParamArray",
        "ArrayItem",
        "HashItem",
        "Module",
        "SubInstance",
        "SubInstanceItem",
        "List",
    }
)

# Plural-collection wrappers collapsed into bare lists in JSON-native
# shape. ``{"Parameter": [...]}`` reduces to ``[...]``.
_PLURAL_COLLAPSE_KEYS = frozenset(
    {
        "Parameter",
        "ParameterItem",
        "ParamArray",
        "Module",
        "SubInstance",
        "SubInstanceItem",
        "List",
    }
)


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------

def _atomic_write_bytes(path: str, data: bytes) -> None:
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)


def _atomic_write_text(path: str, data: str) -> None:
    _atomic_write_bytes(path, data.encode("utf-8"))


# ---------------------------------------------------------------------------
# XML -> dict (XML-shape)
# ---------------------------------------------------------------------------

def _strip_ns(tag: str) -> str:
    if isinstance(tag, str) and tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _element_to_obj(elem: Any, force_list: frozenset[str]) -> Any:
    children = [c for c in list(elem) if isinstance(_strip_ns(c.tag), str)]
    text = elem.text or ""
    text_stripped = text.strip()

    if not children and not elem.attrib:
        return text_stripped

    result: dict[str, Any] = {}
    for k, v in elem.attrib.items():
        result[_strip_ns(k)] = v

    grouped: dict[str, list[Any]] = {}
    for child in children:
        tag = _strip_ns(child.tag)
        grouped.setdefault(tag, []).append(_element_to_obj(child, force_list))

    src = f"line {elem.sourceline}" if getattr(elem, "sourceline", None) else "?"
    for tag, vals in grouped.items():
        if tag in result:
            raise ValueError(
                f"xml_json: attribute/element name collision on '{tag}' "
                f"(near {src}); rename one to make the conversion unambiguous"
            )
        if len(vals) == 1 and tag not in force_list:
            result[tag] = vals[0]
        else:
            result[tag] = vals

    if text_stripped:
        if "_text" in result:
            raise ValueError(
                f"xml_json: '_text' key collision (near {src}); "
                "remove the mixed XML text content"
            )
        result["_text"] = text_stripped

    if not result:
        return text_stripped
    return result


def _read_xml(path: str, force_list: Optional[Iterable[str]] = None) -> dict:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    fl = frozenset(force_list) if force_list is not None else DEFAULT_FORCE_LIST
    tree = _ET.parse(path)
    root = tree.getroot()
    obj = _element_to_obj(root, fl)
    if not isinstance(obj, dict):
        obj = {"_text": obj} if obj else {}
    return {_strip_ns(root.tag): obj}


# ---------------------------------------------------------------------------
# XML-shape -> JSON-native shape
# ---------------------------------------------------------------------------

def _native_array(items_value: Any) -> list:
    if isinstance(items_value, list):
        return [_to_native(v) for v in items_value]
    if isinstance(items_value, dict):
        items = items_value.get("ArrayItem", [])
        if not isinstance(items, list):
            items = [items]
        out = []
        for it in items:
            if not isinstance(it, dict):
                out.append(_to_native(it))
                continue
            if "Val" in it and len(it) == 1:
                out.append(_to_native(it["Val"]))
            elif "ArrayType" in it and len(it) == 1:
                out.append(_native_array(it["ArrayType"]))
            elif "HashType" in it and len(it) == 1:
                out.append(_native_hash(it["HashType"]))
            else:
                out.append(_to_native(it))
        return out
    return [items_value]


def _native_hash(items_value: Any) -> dict:
    if isinstance(items_value, dict) and "HashItem" not in items_value:
        return {k: _to_native(v) for k, v in items_value.items()}
    if isinstance(items_value, dict):
        items = items_value.get("HashItem", [])
        if not isinstance(items, list):
            items = [items]
        out: dict[str, Any] = {}
        for it in items:
            if not isinstance(it, dict) or "Key" not in it:
                raise ValueError(
                    f"_native_hash: malformed HashItem (missing 'Key'): {it!r}"
                )
            key = it["Key"]
            if "Val" in it:
                out[key] = _to_native(it["Val"])
            elif "ArrayType" in it:
                out[key] = _native_array(it["ArrayType"])
            elif "HashType" in it:
                out[key] = _native_hash(it["HashType"])
            else:
                rest = {k: v for k, v in it.items() if k != "Key"}
                out[key] = _to_native(rest)
        return out
    return {}


def _to_native(value: Any) -> Any:
    if isinstance(value, dict):
        if "_text" in value:
            raise ValueError(
                "xml_json: '_text' keys are not representable in JSON; "
                "remove the mixed XML text content first"
            )
        keys = set(value.keys())
        if keys == {"ArrayType"}:
            return _native_array(value["ArrayType"])
        if keys == {"HashType"}:
            return _native_hash(value["HashType"])
        if len(value) == 1:
            ((only_k, only_v),) = value.items()
            if only_k in _PLURAL_COLLAPSE_KEYS:
                if isinstance(only_v, list):
                    return [_to_native(v) for v in only_v]
                return [_to_native(only_v)]
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k == "ArrayType":
                out["__ArrayType__"] = _native_array(v)
            elif k == "HashType":
                out["__HashType__"] = _native_hash(v)
            elif k == "Val":
                out["__Val__"] = _to_native(v)
            else:
                out[k] = _to_native(v)
        return out
    if isinstance(value, list):
        return [_to_native(v) for v in value]
    if isinstance(value, str):
        return _coerce_scalar_str(value)
    return value


def xml_to_json(xml_path: str, json_path: str) -> None:
    """Read XML at ``xml_path``, write JSON-native equivalent at ``json_path``."""
    xml_shape = _read_xml(xml_path)
    native = _to_native(xml_shape)
    # Build full payload first; write atomically so an error mid-serialise
    # leaves the destination untouched.
    payload = json.dumps(native, indent=2, sort_keys=False) + "\n"
    _atomic_write_text(json_path, payload)


# ---------------------------------------------------------------------------
# JSON-native shape -> XML-shape
# ---------------------------------------------------------------------------

def _from_native(value: Any) -> Any:
    """Inverse of :func:`_to_native`. Produces an XML-shape dict suitable
    for :func:`_write_xml`. Lossy on plural collapse: bare lists round-trip
    as repeated sibling elements rather than ``<Singular>`` wrappers."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k == "__ArrayType__":
                items = [_array_item(item) for item in v] if isinstance(v, list) else []
                out["ArrayType"] = {"ArrayItem": items}
            elif k == "__HashType__":
                if isinstance(v, dict):
                    items = [
                        _hash_item(hk, hv) for hk, hv in v.items()
                    ]
                else:
                    items = []
                out["HashType"] = {"HashItem": items}
            elif k == "__Val__":
                out["Val"] = _from_native(v)
            else:
                out[k] = _from_native(v)
        return out
    if isinstance(value, list):
        return [_from_native(v) for v in value]
    return value


def _array_item(item: Any) -> dict:
    if isinstance(item, list):
        return {"ArrayType": {"ArrayItem": [_array_item(i) for i in item]}}
    if isinstance(item, dict):
        return _from_native(item)
    return {"Val": item}


def _hash_item(key: Any, value: Any) -> dict:
    if isinstance(value, list):
        return {"Key": key, "ArrayType": {"ArrayItem": [_array_item(i) for i in value]}}
    if isinstance(value, dict):
        if "__ArrayType__" in value:
            return {"Key": key, "ArrayType": {"ArrayItem": [_array_item(i) for i in value["__ArrayType__"]]}}
        if "__HashType__" in value:
            inner = value["__HashType__"]
            return {"Key": key, "HashType": {"HashItem": [_hash_item(k, v) for k, v in inner.items()]}}
        if "__Val__" in value:
            return {"Key": key, "Val": value["__Val__"]}
        return {"Key": key, **_from_native(value)}
    return {"Key": key, "Val": value}


def _obj_to_element(parent: Any, tag: str, value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _obj_to_element(parent, tag, item)
        return
    elem = _ET.SubElement(parent, tag)
    if isinstance(value, dict):
        text = value.get("_text")
        if text is not None and not isinstance(text, (dict, list)):
            elem.text = str(text)
        for k, v in value.items():
            if k == "_text":
                continue
            _obj_to_element(elem, k, v)
    elif value is None:
        elem.text = ""
    else:
        elem.text = "" if value == "" else str(value)


def _write_xml(tree: dict, path: str, *, root_tag: str = "config") -> None:
    if isinstance(tree, dict) and len(tree) == 1:
        ((rtag, rval),) = tree.items()
    else:
        rtag, rval = root_tag, tree

    root = _ET.Element(rtag)
    if isinstance(rval, dict):
        text = rval.get("_text")
        if text is not None and not isinstance(text, (dict, list)):
            root.text = str(text)
        for k, v in rval.items():
            if k == "_text":
                continue
            _obj_to_element(root, k, v)
    elif rval is None:
        root.text = ""
    else:
        root.text = str(rval)

    if _USING_LXML:
        xml_bytes = _ET.tostring(  # type: ignore[call-arg]
            root, pretty_print=True, xml_declaration=False, encoding="utf-8"
        )
    else:
        try:
            _ET.indent(root)  # type: ignore[attr-defined]
        except AttributeError:
            pass
        xml_bytes = _ET.tostring(root, encoding="utf-8")

    _atomic_write_bytes(path, xml_bytes)


def json_to_xml(json_path: str, xml_path: str) -> None:
    """Read JSON-native at ``json_path``, write XML at ``xml_path``."""
    if not os.path.isfile(json_path):
        raise FileNotFoundError(json_path)
    with open(json_path, "r", encoding="utf-8") as fh:
        native = json.load(fh)
    if not isinstance(native, dict):
        raise ValueError(
            f"{json_path}: top-level JSON value must be an object, got "
            f"{type(native).__name__}"
        )
    xml_shape = _from_native(native)
    _write_xml(xml_shape, xml_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_USAGE = (
    "usage: {prog} INPUT OUTPUT\n"
    "  {prog} converts {direction}.\n"
)


def _main(argv: list[str], mode: str) -> int:
    prog = f"genesispy-{mode}"
    args = argv[1:]
    if len(args) != 2 or args[0] in ("-h", "--help"):
        direction = "XML to JSON" if mode == "xml2json" else "JSON to XML"
        sys.stderr.write(_USAGE.format(prog=prog, direction=direction))
        return 0 if args and args[0] in ("-h", "--help") else 2
    src, dst = args
    if mode == "xml2json":
        xml_to_json(src, dst)
    else:
        json_to_xml(src, dst)
    return 0


def main_xml2json(argv: Optional[list[str]] = None) -> int:
    return _main(list(sys.argv if argv is None else argv), "xml2json")


def main_json2xml(argv: Optional[list[str]] = None) -> int:
    return _main(list(sys.argv if argv is None else argv), "json2xml")
