"""JSON reader/writer for genesispy configuration trees.

JSON-native shape uses double-underscore-bracketed sentinels so user keys
cannot collide with wrapper marker names:

  * Arrays as native lists:   ``"__ArrayType__": [2, 5, 16]``
  * Hashes as native dicts:   ``"__HashType__": {"k": "v"}``
  * Scalar param values:      ``"__Val__": 8``
  * Scalars keep their JSON type (int / float / bool / null / str).

XML support has been factored out to :mod:`genesispy.tools.xml_json`;
convert legacy XML configs once via ``genesispy-xml2json`` before feeding
them to genesispy.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional


def read_json(path: str) -> dict:
    """Load ``path`` and return its contents as a dict.

    The JSON file's top-level object is expected to have a single root key
    (mirroring a Genesis2-style config root), e.g. ``{"HierarchyTop":
    {...}}``. The returned dict is stored as-is in
    ``ConfigHandler._xml_db``; no structural translation is performed.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8") as fh:
        obj = json.load(fh)
    if not isinstance(obj, dict):
        raise ValueError(
            f"{path}: top-level JSON value must be an object, got "
            f"{type(obj).__name__}"
        )
    return obj


def write_json(tree: dict, path: str) -> None:
    """Serialise ``tree`` (JSON-native shape) to ``path``.

    Errors if the input contains ``_text`` keys or non-JSON-serialisable
    values.
    """
    _check_no_text(tree)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(tree, fh, indent=2, sort_keys=False)
        fh.write("\n")


def _check_no_text(value: Any, _seen: Optional[set] = None) -> None:
    if not isinstance(value, (dict, list)):
        return
    if _seen is None:
        _seen = set()
    if id(value) in _seen:
        raise ValueError("write_json: cyclic structure not representable as JSON")
    _seen.add(id(value))
    if isinstance(value, dict):
        if "_text" in value:
            raise ValueError(
                "write_json: '_text' keys are not representable in "
                "JSON-native shape"
            )
        for v in value.values():
            _check_no_text(v, _seen)
    else:
        for v in value:
            _check_no_text(v, _seen)
    _seen.discard(id(value))
