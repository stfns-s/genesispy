"""Stable parameter signatures for module-deduplication.

The Perl Genesis2 implementation hashes the result of ``Data::Dumper`` over
a parameter dict with ``Digest::SHA``.  Here we use a canonical-JSON form
hashed with SHA-256.  The digests are **stable across Python runs** but are
*intentionally* NOT bit-equal to the Perl digests -- a name-translation map
is handled by the gold-diff harness (see Genesis2/test/glctest/).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical(v: Any) -> Any:
    """Return a JSON-serialisable, order-stable representation of ``v``.

    Tuples and lists collapse to the same form: Verilog parameters have
    no notion of tuple-vs-list, so ``unique_inst(F, x=(1,2))`` and
    ``unique_inst(F, x=[1,2])`` deliberately share a dedup signature.
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, str)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_canonical(x) for x in v]
    if isinstance(v, dict):
        # str()-coerced keys must stay distinct: ``{1: ..., "1": ...}`` would
        # otherwise silently collide and lose one value.
        out: dict = {}
        for k in sorted(v, key=str):
            sk = str(k)
            if sk in out:
                raise TypeError(
                    f"_canonical: dict keys collapse under str(): {k!r} vs "
                    f"existing key with same str() form '{sk}'"
                )
            out[sk] = _canonical(v[k])
        return out
    # repr() fallback for class instances passed as params; intra-run only
    # (no cross-run cache). Used by demos/regfile/.../cfg_ifc.vpy.
    return repr(v)


def sha256_param_signature(module_name: str, params: dict) -> str:
    """Canonical-JSON SHA-256 hex digest, stable across Python runs."""
    canon = {
        "module": module_name,
        "params": {k: _canonical(params[k]) for k in sorted(params)},
    }
    blob = json.dumps(
        canon,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
