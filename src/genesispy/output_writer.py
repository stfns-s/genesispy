"""Phase E: persist OUTFILE_CONTENT_CACHE to disk and emit file lists.

This module is the Python port of the output-orchestration tail of
``Manager.pm`` (lines 1100-1500), namely:

* ``create_product_lists``  -> :func:`flush_to_disk` + :func:`write_file_lists`
* ``create_clean_file``     -> :func:`write_clean_script`

Helpers here purposely take a ``Manager``-shaped object (duck-typed).
This keeps the writer decoupled from the real Manager class; see
``tests/_stubs.StubManager`` for the minimal stand-in.  Across this
module the attributes read are:

``debug``, ``depend_file``, ``gen_raw``, ``out_type``, ``output_dir``,
``parsed_source_files``, ``product_file``, ``raw_dir``, ``synth_dir``,
``top``, ``touched_dirs``, ``verif_dir`` -- plus ``src_path``,
``inc_path`` and ``cfg_path``, which :func:`write_pathfile` reads
through ``getattr`` and treats as empty when absent.

Conventions established here (see also docstrings):

* Cache filenames may include or omit a ``.v`` suffix; we append ``.v`` if
  missing so downstream tools always see canonical Verilog file names.
* Synth/verif partitioning is driven by ``cache.OUTFILE_TAGS``, which
  Manager populates from a path-based DFS over the elaborated instance
  tree before flush (mirrors Perl ``Manager.pm:1330-1395``).  Tag values
  are ``'synth'``, ``'verif'``, or ``'synth_and_verif'``.  Files with
  no tag default to ``'verif'`` (matches Perl ``SynthTop=undef``).
  Physical placement: ``'verif'`` -> ``verif_dir``; everything else
  -> ``synth_dir``.
* All files are written UTF-8 with LF line endings.
* Writes are idempotent: identical on-disk content is left untouched
  (matches Perl OutfileName_ContentCache caching behaviour and keeps Make
  timestamps stable).
* Paths inside the ``.vlist`` and ``.depend`` files are emitted relative to
  the current working directory when possible (portable for Make
  consumers); otherwise the absolute path is used.
"""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import sys
from typing import Dict, Iterable, List, TextIO, Tuple, Union

from . import cache


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

_KNOWN_EXTENSIONS = (".v", ".sv", ".vh", ".svh")


def _canonical_filename(
    name: str, suffix: str = ".v", *, extra_known: tuple = ()
) -> str:
    """Append ``suffix`` unless ``name`` already ends in a known Verilog
    extension. Plain dotted names (e.g. ``foo.bar``) get the suffix.

    ``extra_known`` extends :data:`_KNOWN_EXTENSIONS` for this call --
    used by :func:`flush_to_disk` to recognise user-configured output
    extensions (e.g. ``.tv``) so cache keys produced by
    ``UniqueModule._flush_outfile`` aren't double-suffixed.

    Production callers always pass an explicit ``suffix`` matching the
    module class's ``_OUTPUT_SUFFIX``; the ``".v"`` default is a fallback
    for ad-hoc / library callers that have no per-class context.
    """
    known = _KNOWN_EXTENSIONS + tuple(extra_known)
    if name.endswith(known):
        return name
    return name + suffix


def _manager_extra_known(manager) -> tuple:
    """Tuple of output extensions configured on ``manager``'s extension_map.

    Falls back to an empty tuple for shim managers that don't expose one.
    """
    em = getattr(manager, "extension_map", None)
    if not em:
        return ()
    return tuple(set(em.values()) - set(_KNOWN_EXTENSIONS))


def _ensure_dir(path: str) -> None:
    if path:
        os.makedirs(path, exist_ok=True)


def _write_if_changed(path: str, content: str) -> bool:
    """Write ``content`` to ``path`` if it differs.  Returns True if written."""
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8", newline="") as fh:
                existing = fh.read()
        except OSError:
            existing = None
        if existing == content:
            return False
    _ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)
    return True


def _portable_path(path: str) -> str:
    """Return ``path`` relative to cwd when feasible, else absolute."""
    abs_path = os.path.abspath(path)
    try:
        rel = os.path.relpath(abs_path, start=os.getcwd())
    except ValueError:  # pragma: no cover - different drives on Windows
        return abs_path
    # Avoid noisy ``../../..`` chains that escape the cwd.
    if rel.startswith(".." + os.sep) or rel == "..":
        return abs_path
    return rel


def _join_paths(paths: Iterable[str]) -> str:
    """One ``_portable_path`` per line, each terminated by ``\\n``."""
    return "".join(_portable_path(p) + "\n" for p in paths)


def _top_name(manager) -> str:
    return manager.top or "top"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def flush_to_disk(manager) -> Dict[str, Union[List[str], List[Tuple[str, str]]]]:
    """Walk :data:`cache.OUTFILE_CONTENT_CACHE` and write each entry to disk.

    Partitioning follows :data:`cache.OUTFILE_TAGS` (populated by
    Manager): ``'synth'`` and ``'synth_and_verif'`` -> ``synth_dir``;
    ``'verif'`` (and any unmapped file) -> ``verif_dir``.  Returns a dict
    with four keys:

    * ``'synth'``, ``'verif'``, ``'synth_and_verif'``: ``List[str]`` of
      destination paths per tag bucket.
    * ``'ordered'``: ``List[Tuple[str, str]]`` of ``(dest_path, tag)`` in
      DFS first-seen order (keys absent from :data:`cache.OUTFILE_ORDER`
      follow alphabetically).  Used by :func:`write_file_lists` and
      :func:`write_product_lists` to derive all product lists with a
      consistent single ordering.

    Idempotent: an entry whose on-disk content matches the cached
    content is left untouched.  Mirrors Perl
    ``OutfileName_ContentCache`` semantics.
    """
    synth_dir = manager.synth_dir
    verif_dir = manager.verif_dir
    flavor = manager.out_type
    gen_raw = manager.gen_raw
    raw_dir = manager.raw_dir

    written: Dict[str, List[str]] = {
        "synth": [],
        "verif": [],
        "synth_and_verif": [],
        # Ordered sequence of (dest_path, tag) in DFS first-seen order.
        # Keys not present in OUTFILE_ORDER follow alphabetically after all
        # ordered entries (preserves prior sorted behaviour for test-only
        # raw cache entries).  List writers use this for consistent ordering.
        "ordered": [],
    }

    tags: Dict[str, str] = cache.OUTFILE_TAGS

    # Track per-realpath so synth/verif basename collisions warn.
    seen_bases: Dict[Tuple[str, str], str] = {}

    # Build iteration order: DFS-recorded names first (in order), then any
    # remaining cache keys alphabetically.  This way test-only raw entries
    # (no OUTFILE_ORDER entry) keep today's sorted behaviour so existing
    # tests that build tags by hand stay green.
    extra_known = _manager_extra_known(manager)
    order_index = {name: i for i, name in enumerate(cache.OUTFILE_ORDER)}
    all_keys = sorted(
        cache.OUTFILE_CONTENT_CACHE.keys(),
        key=lambda k: (order_index.get(k, len(cache.OUTFILE_ORDER)), k),
    )
    for raw_name in all_keys:
        content = cache.OUTFILE_CONTENT_CACHE[raw_name]
        filename = _canonical_filename(raw_name, extra_known=extra_known)
        base = os.path.basename(filename)

        # Try both raw and suffixed keys (tests register raw, prod registers suffixed).
        tag = tags.get(raw_name) or tags.get(filename) or "verif"

        # gen_raw dumps everything; must run before flavor filter's continue.
        if gen_raw and raw_dir:
            _ensure_dir(raw_dir)
            _write_if_changed(os.path.join(raw_dir, base), content)

        target_dir = verif_dir if tag == "verif" else synth_dir
        if not target_dir:
            # Fall back to output_dir if a target dir is unset; better than
            # silently dropping the file.
            target_dir = manager.output_dir or "."

        # Register before flavor filter so collisions surface even when one side is filtered out.
        try:
            seen_key = (os.path.realpath(target_dir), base)
        except OSError:
            seen_key = (os.path.abspath(target_dir), base)
        prior_tag = seen_bases.get(seen_key)
        if prior_tag is not None and prior_tag != tag:
            from . import reporting as _errors
            _errors.warning(
                f"flush_to_disk: {base!r} written as both "
                f"{prior_tag!r} and {tag!r} into the same directory "
                f"{target_dir!r}; second write will overwrite. "
                f"Use distinct --synth-dir/--verif-dir to keep them separate."
            )
        seen_bases[seen_key] = tag

        # flavor filter: drop pure-verif under 'synth', pure-synth under 'verif';
        # synth_and_verif passes both and lands in synth_dir (Perl parity).
        if flavor == "synth" and tag == "verif":
            continue
        if flavor == "verif" and tag == "synth":
            continue

        _ensure_dir(target_dir)
        dest_path = os.path.join(target_dir, base)
        _write_if_changed(dest_path, content)
        written[tag].append(dest_path)
        written["ordered"].append((dest_path, tag))

    if manager.debug:
        for dest_path, kind in written["ordered"]:
            print(f"output_writer: wrote {kind} -> {dest_path}")

    return written


def write_file_lists(
    manager,
    written: Dict[str, List[str]],
    emit_vlist: bool = True,
) -> Dict[str, str]:
    """Write the simulation file list ``<top>.vlist`` (every emitted file),
    an optional verif-only ``<top>.vlist.verif``, and a Make-style
    ``<top>.depend``.

    ``<top>.vlist`` mirrors Perl's full ``$ProductFileName`` list and
    contains synth + verif + synth_and_verif paths.  ``<top>.vlist.verif``
    is written only when at least one verif-tagged file exists; it lists
    verif + synth_and_verif paths (matching Perl ``Manager.pm:1394``).

    When ``emit_vlist=False`` (caller already requested a named product
    via ``--vf-out`` / ``--product``), the two ``.vlist`` files are
    skipped; only ``<top>.depend`` is written. The depend file then
    targets the named product file path instead of ``<top>.vlist``.

    Returns ``{'synth_vlist': ..., 'verif_vlist': ..., 'depend': ...}``
    (``synth_vlist`` / ``verif_vlist`` omitted when not written).  The
    ``synth_vlist`` key is retained for backward compat though the file
    now holds the full list rather than synth-only.
    """
    output_dir = manager.output_dir or "."
    _ensure_dir(output_dir)
    top = _top_name(manager)

    out: Dict[str, str] = {}

    # Derive all lists from the single DFS-ordered sequence so every product
    # file uses the same order (mirrors Perl Manager.pm:1330-1395 single list
    # filtered per destination).
    ordered: List[Tuple[str, str]] = written.get("ordered", [])
    full_paths = [p for p, _t in ordered]
    verif_list_paths = [p for p, t in ordered if t != "synth"]

    full_vlist = os.path.join(output_dir, f"{top}.vlist")

    if emit_vlist:
        body = _join_paths(full_paths)
        _write_if_changed(full_vlist, body)
        out["synth_vlist"] = full_vlist

        if verif_list_paths:
            verif_vlist = os.path.join(output_dir, f"{top}.vlist.verif")
            body = _join_paths(verif_list_paths)
            _write_if_changed(verif_vlist, body)
            out["verif_vlist"] = verif_vlist

    # Depfile: '<target>: <input1.vpy> <input2.vpy> ...'
    # Target is the .vlist when we emit one, otherwise the named product
    # file the caller is writing instead. Prerequisites are the parsed
    # input templates plus include()'d files -- NOT the --src-path search
    # directories.
    seen: set = set()
    sources: List[str] = []
    for s in list(manager.parsed_source_files) + list(cache.INCLUDED_FILES):
        key = os.path.abspath(s)
        if key not in seen:
            seen.add(key)
            sources.append(s)
    depend_override = manager.depend_file
    depend_path = depend_override or os.path.join(output_dir, f"{top}.depend")
    depend_target = full_vlist if emit_vlist else (manager.product_file or full_vlist)
    portable_sources = [_portable_path(s) for s in sources]
    deps_str = " ".join(portable_sources)
    if deps_str:
        depend_body = f"{_portable_path(depend_target)}: {deps_str}\n"
    else:
        depend_body = f"{_portable_path(depend_target)}:\n"
    # gcc -MP style: one empty target per prerequisite so a deleted or renamed
    # source does not cause "No rule to make target" when a stale depfile is
    # -include'd.
    for src in portable_sources:
        depend_body += f"{src}:\n"
    _write_if_changed(depend_path, depend_body)
    out["depend"] = depend_path

    return out


def _clean_targets(manager) -> tuple[List[str], List[str]]:
    """Return (dirs, files) that clean_outputs / write_clean_script remove.

    ``dirs`` is the raw/synth/verif directory list (falsy entries filtered).
    ``files`` is the list of file-list artifacts under ``output_dir or '.'``.
    The clean script self-removal and ``genesispy_clean.sh`` deletion stay
    at the call sites (asymmetric between in-process clean and shell script).
    """
    output_dir = manager.output_dir or "."
    top = _top_name(manager)
    dirs = [getattr(manager, attr) for attr in ("raw_dir", "synth_dir", "verif_dir")]
    dirs = [d for d in dirs if d]
    files = [
        os.path.join(output_dir, f"{top}.vlist"),
        os.path.join(output_dir, f"{top}.vlist.verif"),
        os.path.join(output_dir, f"{top}.depend"),
    ]
    return dirs, files


def write_clean_script(manager) -> str:
    """Write ``<output_dir>/genesispy_clean.sh`` and return its absolute path.

    The script ``rm -rf``'s the raw, synth, verif dirs and the file lists
    that :func:`write_file_lists` produces.  The script is marked
    executable (mode 0o755).
    """
    output_dir = manager.output_dir or "."
    _ensure_dir(output_dir)

    script_path = os.path.join(output_dir, "genesispy_clean.sh")

    dirs, list_files = _clean_targets(manager)

    # Dedup by realpath so misconfigs like --synth-dir == --verif-dir don't
    # emit duplicate `rm -rf` lines.
    seen_real: set = set()
    targets: List[str] = []
    for d in dirs:
        key = os.path.realpath(d)
        if key in seen_real:
            continue
        seen_real.add(key)
        targets.append(d)

    # shlex.quote: paths with spaces, quotes, $, backticks must not break
    # or inject into the generated script.
    lines = ["#!/bin/sh", "# Auto-generated by genesispy.output_writer", "set -e", ""]
    for d in targets:
        lines.append(f"rm -rf {shlex.quote(d)}")
    for f in list_files:
        lines.append(f"rm -f {shlex.quote(f)}")
    # remove self last
    lines.append(f"rm -f {shlex.quote(script_path)}")
    lines.append("")
    body = "\n".join(lines)

    _write_if_changed(script_path, body)
    # +x best-effort: shared-CI dirs may reject chmod; `sh script.sh` still works.
    try:
        mode = os.stat(script_path).st_mode
        os.chmod(script_path, mode | stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    except OSError:
        pass

    return os.path.abspath(script_path)


def dump_to_stdout(manager, stream: TextIO | None = None) -> None:
    """Concatenate :data:`cache.OUTFILE_CONTENT_CACHE` to ``stream``.

    Used by ``--stdout`` mode. Files are emitted in sorted order with the
    top module (when known) emitted last, each preceded by a
    ``<comment> genesispy: <filename>`` separator (default ``//``,
    overridden by ``--output-comment``) so consumers can split the stream while
    keeping it valid in the target language.
    """
    out = stream if stream is not None else sys.stdout
    top = manager.top
    extra_known = _manager_extra_known(manager)
    style = getattr(manager, "output_comment", "//")
    if isinstance(style, tuple):
        _open, _close = style
        def _sep(name: str) -> str:
            return f"{_open} genesispy: {name} {_close}"
    else:
        def _sep(name: str) -> str:
            return f"{style} genesispy: {name}"

    names = sorted(cache.OUTFILE_CONTENT_CACHE.keys())
    if top:
        # Move any cache entry whose canonical filename stem matches top to the end.
        def _is_top(n: str) -> bool:
            base = os.path.basename(_canonical_filename(n, extra_known=extra_known))
            stem, _ = os.path.splitext(base)
            return stem == top
        names = [n for n in names if not _is_top(n)] + [n for n in names if _is_top(n)]

    for name in names:
        content = cache.OUTFILE_CONTENT_CACHE[name]
        filename = os.path.basename(_canonical_filename(name, extra_known=extra_known))
        out.write(f"{_sep(filename)}\n")
        out.write(content)
        if not content.endswith("\n"):
            out.write("\n")


def clean_outputs(manager) -> None:
    """Programmatic counterpart of :func:`write_clean_script`.

    Removes ``raw_dir``, ``synth_dir``, ``verif_dir`` and the list files
    that this module emits.  Tolerant of missing files/dirs (mirrors
    ``rm -rf``).
    """
    dirs, files = _clean_targets(manager)

    for d in dirs:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)

    if manager.output_dir:
        files = files + [os.path.join(manager.output_dir, "genesispy_clean.sh")]
        for p in files:
            try:
                os.remove(p)
            except OSError:
                # Best-effort; tolerate missing files and permission/transient issues.
                pass


def write_product_lists(
    manager, written: Dict[str, List[str]], base: str,
    single: bool = False,
) -> Dict[str, str]:
    """Write Genesis2-style product file list(s).

    For ``base = "foo.vf"`` with ``single=False`` writes three files:

      foo.vf        - master (every emitted Verilog file)
      foo.synth.vf  - synth-cone files
      foo.verif.vf  - verif-cone files

    With ``single=True`` (the ``--vf-out`` path) only the master file
    is written; no ``.synth``/``.verif`` side-files are produced.

    Extension is split via :func:`os.path.splitext` (last-dot only,
    matches Perl ``Manager.pm:1302-1319``). Per Perl
    ``Manager.pm:1393-1394``, ``synth_and_verif`` files appear in
    *both* synth and verif lists. They also appear once in the master.

    Returns a dict mapping ``"master"``/``"synth"``/``"verif"`` to the
    written paths (``"synth"``/``"verif"`` omitted when ``single``).
    """
    # Derive all lists from the single DFS-ordered sequence (same source as
    # write_file_lists) so membership and ordering are consistent everywhere.
    ordered: List[Tuple[str, str]] = written.get("ordered", [])
    master_paths = [p for p, _t in ordered]
    synth_cone = [p for p, t in ordered if t != "verif"]
    verif_cone = [p for p, t in ordered if t != "synth"]

    out: Dict[str, str] = {}
    _write_if_changed(base, _join_paths(master_paths))
    out["master"] = base

    if single:
        return out

    stem, ext = os.path.splitext(base)
    if not ext:
        synth_path = base + ".synth"
        verif_path = base + ".verif"
    else:
        synth_path = stem + ".synth" + ext
        verif_path = stem + ".verif" + ext

    _write_if_changed(synth_path, _join_paths(synth_cone))
    out["synth"] = synth_path
    _write_if_changed(verif_path, _join_paths(verif_cone))
    out["verif"] = verif_path

    return out


def write_pathfile(manager, path: str) -> str:
    """Write the list of directories touched during elaboration to ``path``."""
    dirs: List[str] = []
    for attr in ("src_path", "inc_path", "cfg_path"):
        for d in getattr(manager, attr):
            ad = os.path.abspath(d)
            if ad not in dirs:
                dirs.append(ad)
    for d in manager.touched_dirs:
        if d not in dirs:
            dirs.append(d)
    body = _join_paths(dirs)
    _write_if_changed(path, body)
    return path


__all__ = [
    "flush_to_disk",
    "write_file_lists",
    "write_clean_script",
    "clean_outputs",
    "dump_to_stdout",
    "write_product_lists",
    "write_pathfile",
]
