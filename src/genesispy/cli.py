"""Command-line interface for genesispy.

GNU-style long options (``--input``, ``--top``, ...) with a curated set of
POSIX short flags. Departs from Genesis2's Perl single-dash long flags.
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from typing import List, Optional, Sequence, Tuple

from genesispy import __version__
from genesispy import reporting
from genesispy.reporting import warning
from genesispy.extensions import parse_extension_spec


_LISTFILE_DIRECTIVES = {
    "--input": "input",
    "--input-list": "input-list",
    "--src-path": "src-path",
    "--inc-path": "inc-path",
}

# Deprecated listfile directive spellings -> canonical spelling.
_LISTFILE_DEPRECATED = {
    "--inputlist": "--input-list",
    "--srcpath": "--src-path",
    "--includepath": "--inc-path",
}


# Module-level guard so each deprecated alias warns at most once per process.
_warned_aliases: set = set()


def _reset_deprecation_warnings() -> None:
    """Clear the one-time-per-flag deprecation guard. Test hook."""
    _warned_aliases.clear()


def _emit_deprecation(prog: str, old: str, new: str) -> None:
    if old in _warned_aliases:
        return
    _warned_aliases.add(old)
    reporting.warning(f"{prog}: {old} is deprecated; use {new}")


class _DeprStoreAction(argparse.Action):
    """Deprecated alias: stores a single value (like the default store action)."""

    def __init__(self, option_strings, dest, *, new_flag, prog="genesispy", **kw):
        self._new = new_flag
        self._prog = prog
        kw.setdefault("default", argparse.SUPPRESS)
        super().__init__(option_strings, dest, help=argparse.SUPPRESS, **kw)

    def __call__(self, parser, namespace, values, option_string=None):
        _emit_deprecation(self._prog, option_string, self._new)
        setattr(namespace, self.dest, values)


class _DeprAppendAction(argparse.Action):
    """Deprecated alias: appends a value (like ``action='append'``)."""

    def __init__(self, option_strings, dest, *, new_flag, prog="genesispy", **kw):
        self._new = new_flag
        self._prog = prog
        kw.setdefault("default", argparse.SUPPRESS)
        super().__init__(option_strings, dest, help=argparse.SUPPRESS, **kw)

    def __call__(self, parser, namespace, values, option_string=None):
        _emit_deprecation(self._prog, option_string, self._new)
        items = getattr(namespace, self.dest, None)
        if items is None:
            items = []
        items = list(items)
        items.append(values)
        setattr(namespace, self.dest, items)


class _DeprStoreTrueAction(argparse.Action):
    """Deprecated alias: sets a flag to True (like ``action='store_true'``)."""

    def __init__(self, option_strings, dest, *, new_flag, prog="genesispy", **kw):
        self._new = new_flag
        self._prog = prog
        kw.setdefault("default", argparse.SUPPRESS)
        super().__init__(
            option_strings,
            dest,
            nargs=0,
            help=argparse.SUPPRESS,
            **kw,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        _emit_deprecation(self._prog, option_string, self._new)
        setattr(namespace, self.dest, True)


def _add_deprecated_alias(
    parser_or_group,
    old_flags,
    new_flag: str,
    dest: str,
    *,
    kind: str = "store",
    prog: str = "genesispy",
    type=None,
    choices=None,
    metavar=None,
) -> None:
    """Register one or more deprecated aliases that forward to ``dest``.

    ``kind`` is ``"store"``, ``"append"`` or ``"store_true"``. Each old flag
    emits a one-time stderr warning naming ``new_flag``. ``help`` is always
    SUPPRESS so the alias is hidden from both the ``usage:`` synopsis and
    the body of ``--help``.
    """
    if isinstance(old_flags, str):
        old_flags = [old_flags]
    extras = {}
    if type is not None:
        extras["type"] = type
    if choices is not None:
        extras["choices"] = choices
    if metavar is not None:
        extras["metavar"] = metavar
    if kind == "store":
        action_cls = _DeprStoreAction
    elif kind == "append":
        action_cls = _DeprAppendAction
    elif kind == "store_true":
        action_cls = _DeprStoreTrueAction
        # store_true has no value, so type/choices/metavar are nonsensical.
        extras = {}
    else:
        raise ValueError(f"_add_deprecated_alias: unknown kind {kind!r}")

    parser_or_group.add_argument(
        *old_flags,
        action=action_cls,
        dest=dest,
        new_flag=new_flag,
        prog=prog,
        **extras,
    )


def _comment_arg(raw: str) -> str:
    """argparse ``type=`` validator for ``--comment``.

    Rejects empty/whitespace-only values: an empty prefix collapses the
    directive sentinel to bare ``;`` and emits banner lines without any
    comment marker.
    """
    if not raw.strip():
        raise argparse.ArgumentTypeError(
            f"--comment {raw!r}: empty/whitespace-only comment prefix"
        )
    return raw


def _output_comment_arg(raw: str):
    """argparse ``type=`` for ``--output-comment``.

    A ``,`` splits the value into ``(open, close)`` block delimiters; both
    halves must be non-empty. Without a ``,`` the value is a line prefix.
    Empty/whitespace-only values (or halves) are rejected.
    """
    if "," in raw:
        open_d, _, close_d = raw.partition(",")
        if not open_d.strip() or not close_d.strip():
            raise argparse.ArgumentTypeError(
                f"--output-comment {raw!r}: both OPEN and CLOSE must be "
                f"non-empty (form 'OPEN,CLOSE')"
            )
        return (open_d, close_d)
    if not raw.strip():
        raise argparse.ArgumentTypeError(
            f"--output-comment {raw!r}: empty/whitespace-only comment prefix"
        )
    return raw


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="genesispy",
        description="Genesis Chip Generator (Python port of Genesis2)",
        allow_abbrev=False,
    )

    # ------------------------------------------------------------------ #
    # Inputs                                                              #
    # ------------------------------------------------------------------ #
    g_in = parser.add_argument_group("Inputs")
    g_in.add_argument(
        "-i", "--input",
        action="append",
        default=[],
        metavar="FILE",
        help="Source file to process (may be repeated).",
    )
    g_in.add_argument(
        "-f", "--input-list",
        dest="input_list",
        action="append",
        default=[],
        metavar="FILE",
        help=(
            "File containing a list of inputs (may be repeated). Each line "
            "is either a bare path (treated as --input) or a GNU directive "
            "--input/--input-list/--src-path/--inc-path. Inline '# ...' "
            "comments are stripped; --input-list may recurse."
        ),
    )
    _add_deprecated_alias(
        g_in,
        ["-l", "--inputlist"],
        "-f/--input-list",
        dest="input_list",
        kind="append",
        metavar="FILE",
    )
    g_in.add_argument(
        "-t", "--top",
        default=None,
        metavar="NAME",
        help="Name of the top module.",
    )
    g_in.add_argument(
        "--synth-top",
        dest="synth_top",
        default=None,
        metavar="PATH",
        help=(
            "Synthesis-top instance: a top-level instance name "
            "(e.g. 'foo') or dotted instance path (e.g. 'top.foo.bar'). "
            "Files at/under this instance are tagged 'synth'; everything "
            "else is 'verif'. Default: unset -> all files tagged 'verif'."
        ),
    )
    _add_deprecated_alias(
        g_in, "--synthtop", "--synth-top", dest="synth_top", metavar="PATH"
    )
    g_in.add_argument(
        "-p", "--parameter",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Command-line parameter override (may be repeated).",
    )
    g_in.add_argument(
        "-j", "--json-cfg",
        dest="json_cfg",
        default=None,
        metavar="FILE",
        help=(
            "Input JSON configuration file. "
            "(Legacy XML configs: convert with genesispy-xml2json first.)"
        ),
    )
    _add_deprecated_alias(
        g_in, "--json", "-j/--json-cfg", dest="json_cfg", metavar="FILE"
    )
    g_in.add_argument(
        "--cfg", "--py-cfg",
        action="append",
        default=[],
        metavar="FILE",
        help="Input .cfg Python script (may be repeated). Alias: --py-cfg.",
    )

    # ------------------------------------------------------------------ #
    # Search paths                                                        #
    # ------------------------------------------------------------------ #
    g_path = parser.add_argument_group("Search paths")
    g_path.add_argument(
        "--cfg-path",
        dest="cfg_path",
        action="append",
        default=[],
        metavar="DIR",
        help="Search directory for --cfg/--json-cfg inputs (may be repeated).",
    )
    _add_deprecated_alias(
        g_path, "--cfgpath", "--cfg-path", dest="cfg_path",
        kind="append", metavar="DIR",
    )
    g_path.add_argument(
        "--src-path",
        dest="src_path",
        action="append",
        default=[],
        metavar="DIR",
        help=".vpy/source search directory (may be repeated).",
    )
    _add_deprecated_alias(
        g_path, "--srcpath", "--src-path", dest="src_path",
        kind="append", metavar="DIR",
    )
    g_path.add_argument(
        "--inc-path",
        dest="inc_path",
        action="append",
        default=[],
        metavar="DIR",
        help="Include search directory (may be repeated).",
    )
    _add_deprecated_alias(
        g_path, "--includepath", "--inc-path", dest="inc_path",
        kind="append", metavar="DIR",
    )
    g_path.add_argument(
        "--py-path",
        dest="py_path",
        action="append",
        default=[],
        metavar="DIR",
        help="Prepend DIR to sys.path before parsing (may be repeated).",
    )
    _add_deprecated_alias(
        g_path, "--pythonpath", "--py-path", dest="py_path",
        kind="append", metavar="DIR",
    )
    g_path.add_argument(
        "--py-import",
        dest="py_import",
        action="append",
        default=[],
        metavar="NAME",
        help="Import a Python module before parsing (may be repeated).",
    )
    _add_deprecated_alias(
        g_path, "--pymodule", "--py-import", dest="py_import",
        kind="append", metavar="NAME",
    )

    # ------------------------------------------------------------------ #
    # Output selection                                                    #
    # ------------------------------------------------------------------ #
    g_out = parser.add_argument_group("Output selection")
    g_out.add_argument(
        "--out-type",
        dest="out_type",
        choices=("synth", "verif", "both"),
        default="both",
        help="Which output flavour to emit (default: both).",
    )
    _add_deprecated_alias(
        g_out, "--flavor", "--out-type", dest="out_type",
        choices=("synth", "verif", "both"),
    )
    g_out.add_argument(
        "--product",
        default=None,
        metavar="FILE",
        help=(
            "Write Genesis2-style product file lists. --product FILE.ext "
            "produces three files: FILE.ext (all modules), "
            "FILE.synth.ext (synth modules), FILE.verif.ext (verif "
            "modules). Suppresses the default <top>.vlist/<top>.vlist.verif. "
            "Mirrors Genesis2 Manager.pm:1302-1319."
        ),
    )
    g_out.add_argument(
        "--vf-out",
        dest="vf_out",
        default=None,
        metavar="FILE",
        help=(
            "Write a single Verilog file-list product to FILE "
            "(auto-appends .vf if missing). Unlike --product, no "
            ".synth/.verif side-files are emitted. Suppresses the "
            "default <top>.vlist/<top>.vlist.verif. Mutually exclusive "
            "with --product."
        ),
    )
    g_out.add_argument(
        "--depend",
        default=None,
        metavar="FILE",
        help="Override the dependency-list output path (default: <top>.depend).",
    )
    g_out.add_argument(
        "--path",
        default=None,
        metavar="FILE",
        help="Write the list of directories touched during elaboration to FILE.",
    )
    _add_deprecated_alias(
        g_out, "--pathfile", "--path", dest="path", metavar="FILE"
    )
    g_out.add_argument(
        "--log",
        default="genesispy.log",
        metavar="FILE",
        help=(
            "Tee error/warning messages to FILE (default genesispy.log, "
            "lazy-opened on first error/warning). Mirrors Perl LogFileName "
            "(Manager.pm:103). Suppress by passing /dev/null."
        ),
    )
    g_out.add_argument(
        "--json-out",
        dest="json_out",
        default=None,
        metavar="FILE",
        help=(
            "Write a HierarchyTop snapshot of the elaborated module tree. "
            "Produces three files: FILE (full), <stem>-small<ext> "
            "(no ImmutableParameters), <stem>-tiny<ext> "
            "(only user-overridden params, priority >= EXTERNAL_PARAM_FILE), "
            "where <stem>/<ext> are splitext(FILE). "
            "Requires elaboration; skipped under --parse-only."
        ),
    )
    _add_deprecated_alias(
        g_out, "--jsonout", "--json-out", dest="json_out", metavar="FILE"
    )

    # ------------------------------------------------------------------ #
    # Output directories                                                  #
    # ------------------------------------------------------------------ #
    g_dir = parser.add_argument_group("Output directories")
    g_dir.add_argument(
        "--out-dir",
        dest="out_dir",
        default=None,
        metavar="DIR",
        help=(
            "Output directory (default: genesis_synth). When set, also "
            "supplies the default for --synth-dir and --verif-dir."
        ),
    )
    _add_deprecated_alias(
        g_dir, "--outputdir", "--out-dir", dest="out_dir", metavar="DIR"
    )
    g_dir.add_argument(
        "--synth-dir",
        dest="synth_dir",
        default=None,
        metavar="DIR",
        help=(
            "Directory for synth-tagged Verilog (default: --out-dir if "
            "set, else genesis_synth)."
        ),
    )
    g_dir.add_argument(
        "--verif-dir",
        dest="verif_dir",
        default=None,
        metavar="DIR",
        help=(
            "Directory for verif-tagged Verilog (default: --out-dir if "
            "set, else genesis_verif)."
        ),
    )

    # ------------------------------------------------------------------ #
    # Phases / caching                                                    #
    # ------------------------------------------------------------------ #
    g_phase = parser.add_argument_group("Phases / caching")
    g_phase.add_argument(
        "--clean",
        action="store_true",
        default=False,
        help="Delete generated files and exit.",
    )
    g_phase.add_argument(
        "--parse-only",
        dest="parse_only",
        action="store_true",
        default=False,
        help="Run only the parse phase (.vpy -> generated .py).",
    )
    g_phase.add_argument(
        "--gen-only",
        dest="gen_only",
        action="store_true",
        default=False,
        help="Skip the parse phase; expect generated .py files already present.",
    )
    _add_deprecated_alias(
        g_phase, "--generate-only", "--gen-only", dest="gen_only",
        kind="store_true",
    )
    g_phase.add_argument(
        "--no-module-cache",
        dest="no_module_cache",
        action="store_true",
        default=False,
        help="Disable the unique-module dedup cache (forces fresh modules).",
    )
    g_phase.add_argument(
        "--gen-raw",
        dest="gen_raw",
        action="store_true",
        default=False,
        help=(
            "Also emit the unprocessed Verilog into raw_dir "
            "(./genesis_raw/ by default; relocated under --use-tmp)."
        ),
    )
    g_phase.add_argument(
        "--raw-dir",
        dest="raw_dir",
        default=None,
        metavar="DIR",
        help=(
            "Override the raw_dir location (default: ./genesis_raw). "
            "Mutually exclusive with --use-tmp/--keep-tmp. The directory "
            "persists after the run; --clean and --stdout remove it."
        ),
    )
    g_phase.add_argument(
        "--use-tmp",
        dest="use_tmp",
        action="store_true",
        default=False,
        help="Place work/raw directories under a /tmp scratch dir.",
    )
    g_phase.add_argument(
        "--keep-tmp",
        dest="keep_tmp",
        action="store_true",
        default=False,
        help="Keep the /tmp scratch dir after exit (implies --use-tmp).",
    )

    # ------------------------------------------------------------------ #
    # Template / target language                                          #
    # ------------------------------------------------------------------ #
    g_tmpl = parser.add_argument_group("Template / target language")
    g_tmpl.add_argument(
        "--extension",
        dest="extensions",
        action="append",
        default=[],
        type=parse_extension_spec,
        metavar="EXT_IN=EXT_OUT",
        help=(
            "Pair an input template extension with its emitted-Verilog "
            "extension (may be repeated). Defaults: .vpy=.v, .svpy=.sv. "
            "User entries override defaults; e.g. '--extension .vpy=.sv' "
            "or '--extension .tvpy=.tv'."
        ),
    )
    g_tmpl.add_argument(
        "-sv", "--system-verilog",
        dest="system_verilog",
        action="store_true",
        default=False,
        help="Shorthand for '--extension .vpy=.sv'.",
    )
    _add_deprecated_alias(
        g_tmpl, "--systemverilog", "-sv/--system-verilog",
        dest="system_verilog", kind="store_true",
    )
    g_tmpl.add_argument(
        "--source-comment",
        dest="source_comment",
        default="//",
        type=_comment_arg,
        help=(
            "Line-comment prefix of the source/target language (default "
            "\"//\"). Sets both the directive sentinel ('<comment>;' replaces "
            "'//;') and, unless --output-comment is given, the emitted module "
            "banner prefix."
        ),
    )
    _add_deprecated_alias(
        g_tmpl, "--comment", "--source-comment", dest="source_comment",
        kind="store", type=_comment_arg,
    )
    g_tmpl.add_argument(
        "--output-comment",
        dest="output_comment",
        default=None,
        type=_output_comment_arg,
        metavar="PREFIX | OPEN,CLOSE",
        help=(
            "Comment style for genesispy-emitted output comments (module "
            "banner and the --stdout 'genesispy:' separator). A line prefix "
            "(e.g. '#') or a block form 'OPEN,CLOSE' (e.g. '/*,*/'). "
            "Defaults to --source-comment."
        ),
    )
    g_tmpl.add_argument(
        "--param-footer",
        dest="param_footer",
        action="store_true",
        default=False,
        help=(
            "Append a comment block after each generated module listing every "
            "resolved parameter with its value and the configuration source it "
            "came from. Unlike the module banner, this is written after the "
            "template body runs, so it sees the fully resolved parameter set."
        ),
    )
    g_tmpl.add_argument(
        "-j2", "--j2",
        action="store_true",
        default=False,
        help=(
            "Parse templates with the j2 (Jinja2-like) flavour. Shares "
            "delimiters with stock Jinja2 -- '{%% stmt %%}' replaces "
            "'//; stmt', '{{ expr }}' replaces backticks, '{# comment #}' "
            "is a stripped comment -- but with expanded semantics: the "
            "embedded language is full Python (no filter pipes, no "
            "'is'-tests, no macro/block/extends). Stock Jinja2 sources "
            "do not parse here as-is; see 'genesispy-jinja2j2' to port "
            "them."
        ),
    )

    # ------------------------------------------------------------------ #
    # Misc                                                                #
    # ------------------------------------------------------------------ #
    g_misc = parser.add_argument_group("Misc")
    g_misc.add_argument(
        "--unq-style",
        dest="unq_style",
        choices=("numeric", "param"),
        default="numeric",
        help=(
            "Module uniquification style: 'numeric' (default; foo_unq1) "
            "or 'param' (foo_N4). Used by generate(...) dispatch."
        ),
    )
    _add_deprecated_alias(
        g_misc, "--unqstyle", "--unq-style", dest="unq_style",
        choices=("numeric", "param"),
    )
    g_misc.add_argument(
        "-d", "--debug",
        type=int,
        default=0,
        metavar="LEVEL",
        help="Debug verbosity level (default: 0).",
    )
    g_misc.add_argument(
        "--stdout",
        action="store_true",
        default=False,
        help=(
            "Write generated Verilog to stdout instead of "
            "genesis_synth/genesis_verif. Skips .vlist/.depend/clean script "
            "and removes the raw_dir on exit. --json-out still writes its "
            "files (snapshot is independent of Verilog mode)."
        ),
    )
    g_misc.add_argument(
        "-v", "--version",
        action="version",
        version=f"genesispy {__version__}",
    )
    return parser


def _strip_inline_comment(line: str) -> str:
    """Remove an inline ``# ...`` comment from ``line``.

    A ``#`` only counts as a comment marker when (a) at column 0 or
    preceded by whitespace, and (b) outside single/double quotes.
    ``foo#bar`` is a literal token; ``foo #bar`` strips to ``foo``;
    ``"foo bar#baz"`` keeps the ``#`` because it is quoted.
    """
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif (
            ch == "#"
            and not in_s
            and not in_d
            and (i == 0 or line[i - 1].isspace())
        ):
            return line[:i]
    return line


def _parse_listfile_line(raw: str) -> Tuple[Optional[str], List[str]]:
    """Parse one listfile line into ``(directive, tokens)``.

    Returns ``(None, [])`` for blank/comment-only lines. ``directive`` is
    one of the canonical keys of :data:`_LISTFILE_DIRECTIVES` (deprecated
    spellings are rewritten and warned) or ``None`` (bare paths default
    to ``--input``).
    """
    cleaned = _strip_inline_comment(raw).strip()
    if not cleaned:
        return None, []
    tokens = shlex.split(cleaned, posix=True)
    if not tokens:
        return None, []
    head = tokens[0]
    if head in _LISTFILE_DEPRECATED:
        canonical = _LISTFILE_DEPRECATED[head]
        _emit_deprecation("genesispy", head, canonical)
        return canonical, tokens[1:]
    if head in _LISTFILE_DIRECTIVES:
        return head, tokens[1:]
    return None, tokens


def _expand_listfiles(
    listfiles: List[str],
    parser: argparse.ArgumentParser,
    *,
    ancestors: Optional[tuple] = None,
    processed: Optional[set] = None,
) -> Tuple[List[str], List[str], List[str]]:
    """Recursively expand ``--input-list`` files.

    Returns ``(inputs, srcpaths, includepaths)`` accumulated across all
    listfiles in order. True cycles (a listfile that is its own ancestor)
    raise via ``parser.error``. A listfile that has already been fully
    expanded (diamond / repeated reference) is skipped silently — no error,
    no duplicate inputs. Empty listfiles (no inputs produced) emit a warning.
    Duplicate input paths (within or across listfiles) emit a warning but are
    kept.

    ``ancestors`` is a tuple of realpaths on the current recursion stack, used
    to detect true cycles.  ``processed`` is a shared set of realpaths that
    have already been fully expanded, used to skip diamonds silently.
    """
    if ancestors is None:
        ancestors = ()
    if processed is None:
        processed = set()
    inputs: List[str] = []
    srcpaths: List[str] = []
    incpaths: List[str] = []

    for lf in listfiles:
        # realpath, not abspath: resolve symlinks so a symlinked loop
        # also trips cycle detection.
        try:
            abs_lf = os.path.realpath(lf)
        except OSError as exc:
            parser.error(f"--input-list: cannot resolve {lf!r}: {exc}")
        if abs_lf in ancestors:
            parser.error(f"--input-list: cycle detected on {lf!r}")
        # Already fully expanded in a prior branch (diamond / repeated ref) —
        # skip silently to avoid duplicates and spurious empty-list warnings.
        if abs_lf in processed:
            continue

        try:
            with open(lf, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError as exc:
            parser.error(f"--input-list: cannot read {lf!r}: {exc}")

        produced_inputs = 0
        child_ancestors = ancestors + (abs_lf,)
        for lineno, raw in enumerate(lines, 1):
            directive, tokens = _parse_listfile_line(raw)
            if not tokens:
                continue
            if directive is None or directive == "--input":
                inputs.extend(tokens)
                produced_inputs += len(tokens)
            elif directive == "--input-list":
                sub_in, sub_src, sub_inc = _expand_listfiles(
                    tokens, parser, ancestors=child_ancestors, processed=processed
                )
                inputs.extend(sub_in)
                srcpaths.extend(sub_src)
                incpaths.extend(sub_inc)
                produced_inputs += len(sub_in)
            elif directive == "--src-path":
                srcpaths.extend(tokens)
            elif directive == "--inc-path":
                incpaths.extend(tokens)
            else:  # pragma: no cover - guarded by directive lookup
                parser.error(
                    f"--input-list {lf!r}:{lineno}: unknown directive {directive!r}"
                )

        processed.add(abs_lf)
        if produced_inputs == 0:
            warning(f"--input-list: {lf} contributed no inputs")

    return inputs, srcpaths, incpaths


def _warn_duplicate_inputs(inputs: Sequence[str]) -> None:
    seen: dict = {}
    for p in inputs:
        key = os.path.abspath(p)
        seen[key] = seen.get(key, 0) + 1
    for key, count in seen.items():
        if count > 1:
            warning(f"--input: duplicate path {key} ({count} occurrences)")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse ``argv`` (defaults to ``sys.argv[1:]``) into a Namespace."""
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.parse_only and args.gen_only:
        parser.error("--parse-only and --gen-only are mutually exclusive")
    if args.keep_tmp:
        args.use_tmp = True
    if args.raw_dir is not None and args.use_tmp:
        parser.error("--raw-dir is mutually exclusive with --use-tmp/--keep-tmp")
    # -sv is shorthand for '--extension .vpy=.sv'. If the user already passed
    # any explicit .vpy mapping with a different output extension, raise; if
    # they passed exactly .vpy=.sv it's a redundant no-op.
    if args.system_verilog:
        vpy_outs = [out for (in_ext, out) in args.extensions if in_ext == ".vpy"]
        non_sv = [out for out in vpy_outs if out != ".sv"]
        if non_sv:
            parser.error(
                f"-sv requests '.vpy=.sv' but --extension .vpy={non_sv[0]} "
                f"was also given; mappings conflict."
            )
        if not vpy_outs:
            args.extensions.append((".vpy", ".sv"))

    if args.input_list:
        extra_in, extra_src, extra_inc = _expand_listfiles(args.input_list, parser)
        # -i entries first, then listfile contents in --input-list order.
        args.input = list(args.input) + extra_in
        args.src_path = list(args.src_path) + extra_src
        args.inc_path = list(args.inc_path) + extra_inc
        _warn_duplicate_inputs(args.input)

    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point.  Returns a process exit code."""
    args = parse_args(argv)
    # Local import to avoid a circular dep if Manager ever imports cli.
    from .manager import Manager

    mgr = Manager(args)
    return mgr.execute()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
