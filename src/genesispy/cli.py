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
from genesispy.errors import warning
from genesispy.extensions import parse_extension_spec


_LISTFILE_DIRECTIVES = {
    "--input": "input",
    "--inputlist": "inputlist",
    "--srcpath": "srcpath",
    "--includepath": "includepath",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="genesispy",
        description="Genesis Chip Generator (Python port of Genesis2)",
        allow_abbrev=False,
    )

    parser.add_argument(
        "-i", "--input",
        action="append",
        default=[],
        metavar="FILE",
        help="Source file to process (may be repeated).",
    )
    parser.add_argument(
        "-l", "--inputlist",
        action="append",
        default=[],
        metavar="FILE",
        help=(
            "File containing a list of inputs (may be repeated). Each line "
            "is either a bare path (treated as --input) or a GNU directive "
            "--input/--inputlist/--srcpath/--includepath. Inline '# ...' "
            "comments are stripped; --inputlist may recurse."
        ),
    )
    parser.add_argument(
        "-t", "--top",
        default=None,
        metavar="NAME",
        help="Name of the top module.",
    )
    parser.add_argument(
        "--synthtop",
        default=None,
        metavar="PATH",
        help=(
            "Synthesis-top instance: a top-level instance name "
            "(e.g. 'foo') or dotted instance path (e.g. 'top.foo.bar'). "
            "Files at/under this instance are tagged 'synth'; everything "
            "else is 'verif'. Default: unset -> all files tagged 'verif'."
        ),
    )
    parser.add_argument(
        "-p", "--parameter",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Command-line parameter override (may be repeated).",
    )
    parser.add_argument(
        "-j", "--json",
        default=None,
        metavar="FILE",
        help=(
            "Input JSON configuration file. "
            "(Legacy XML configs: convert with genesispy-xml2json first.)"
        ),
    )
    parser.add_argument(
        "--jsonout",
        default=None,
        metavar="FILE",
        help=(
            "Write a HierarchyTop snapshot of the elaborated module tree. "
            "Produces three files: FILE (full), small_<basename(FILE)> "
            "(no ImmutableParameters), tiny_<basename(FILE)> "
            "(only user-overridden params, priority >= EXTERNAL_XML). "
            "Requires elaboration; skipped under --parse-only."
        ),
    )
    parser.add_argument(
        "--cfg",
        action="append",
        default=[],
        metavar="FILE",
        help="Input .cfg script (may be repeated).",
    )
    parser.add_argument(
        "--cfgpath",
        action="append",
        default=[],
        metavar="DIR",
        help="Search directory for --cfg/--json inputs (may be repeated).",
    )
    parser.add_argument(
        "--srcpath",
        action="append",
        default=[],
        metavar="DIR",
        help=".vpy/source search directory (may be repeated).",
    )
    parser.add_argument(
        "--includepath",
        action="append",
        default=[],
        metavar="DIR",
        help="Include search directory (may be repeated).",
    )
    parser.add_argument(
        "--pythonpath",
        action="append",
        default=[],
        metavar="DIR",
        help="Prepend DIR to sys.path before parsing (may be repeated).",
    )
    parser.add_argument(
        "--pymodule",
        action="append",
        default=[],
        metavar="NAME",
        help="Import a Python module before parsing (may be repeated).",
    )
    parser.add_argument(
        "--flavor",
        choices=("synth", "verif", "both"),
        default="both",
        help="Which output flavour to emit (default: both).",
    )
    parser.add_argument(
        "--product",
        default=None,
        metavar="FILE",
        help=(
            "Write product file lists FILE.synth and FILE.verif "
            "(Genesis2 -product semantics)."
        ),
    )
    parser.add_argument(
        "--depend",
        default=None,
        metavar="FILE",
        help="Override the dependency-list output path (default: <top>.depend).",
    )
    parser.add_argument(
        "--pathfile",
        default=None,
        metavar="FILE",
        help="Write the list of directories touched during elaboration to FILE.",
    )
    parser.add_argument(
        "--log",
        default=None,
        metavar="FILE",
        help="Tee error/warning messages to FILE (in addition to stderr).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        default=False,
        help="Delete generated files and exit.",
    )
    parser.add_argument(
        "--parse-only",
        dest="parse_only",
        action="store_true",
        default=False,
        help="Run only the parse phase (.vpy -> generated .py).",
    )
    parser.add_argument(
        "--generate-only",
        dest="generate_only",
        action="store_true",
        default=False,
        help="Skip the parse phase; expect generated .py files already present.",
    )
    parser.add_argument(
        "--no-module-cache",
        dest="no_module_cache",
        action="store_true",
        default=False,
        help="Disable the unique-module dedup cache (forces fresh modules).",
    )
    parser.add_argument(
        "--gen-raw",
        dest="gen_raw",
        action="store_true",
        default=False,
        help="Also emit the unprocessed Verilog into raw_dir (./genesis_raw/ by default; relocated under --use-tmp).",
    )
    parser.add_argument(
        "--use-tmp",
        dest="use_tmp",
        action="store_true",
        default=False,
        help="Place work/raw directories under a /tmp scratch dir.",
    )
    parser.add_argument(
        "--keep-tmp",
        dest="keep_tmp",
        action="store_true",
        default=False,
        help="Keep the /tmp scratch dir after exit (implies --use-tmp).",
    )
    parser.add_argument(
        "-d", "--debug",
        type=int,
        default=0,
        metavar="LEVEL",
        help="Debug verbosity level (default: 0).",
    )
    parser.add_argument(
        "--unqstyle",
        choices=("numeric", "param"),
        default="numeric",
        help=(
            "Module uniquification style: 'numeric' (default; foo_unq1) "
            "or 'param' (foo_N4). Used by generate(...) dispatch."
        ),
    )
    parser.add_argument(
        "--outputdir",
        default=None,
        metavar="DIR",
        help=(
            "Output directory (default: genesis_synth). When set, also "
            "supplies the default for --synth-dir and --verif-dir."
        ),
    )
    parser.add_argument(
        "--synth-dir",
        dest="synth_dir",
        default=None,
        metavar="DIR",
        help=(
            "Directory for synth-tagged Verilog (default: --outputdir if "
            "set, else genesis_synth)."
        ),
    )
    parser.add_argument(
        "--verif-dir",
        dest="verif_dir",
        default=None,
        metavar="DIR",
        help=(
            "Directory for verif-tagged Verilog (default: --outputdir if "
            "set, else genesis_verif)."
        ),
    )
    parser.add_argument(
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
    parser.add_argument(
        "-sv", "--systemverilog",
        action="store_true",
        default=False,
        help="Shorthand for '--extension .vpy=.sv'.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        default=False,
        help=(
            "Write generated Verilog to stdout instead of "
            "genesis_synth/genesis_verif. Skips .vlist/.depend/clean script "
            "and removes the raw_dir on exit. --jsonout still writes its "
            "files (snapshot is independent of Verilog mode)."
        ),
    )
    parser.add_argument(
        "--version",
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
    one of the keys of :data:`_LISTFILE_DIRECTIVES` or ``None`` (bare paths
    default to ``--input``).
    """
    cleaned = _strip_inline_comment(raw).strip()
    if not cleaned:
        return None, []
    tokens = shlex.split(cleaned, posix=True)
    if not tokens:
        return None, []
    head = tokens[0]
    if head in _LISTFILE_DIRECTIVES:
        return head, tokens[1:]
    return None, tokens


def _expand_listfiles(
    listfiles: List[str],
    parser: argparse.ArgumentParser,
    *,
    seen: Optional[set] = None,
) -> Tuple[List[str], List[str], List[str]]:
    """Recursively expand ``--inputlist`` files.

    Returns ``(inputs, srcpaths, includepaths)`` accumulated across all
    listfiles in order. Cycles raise via ``parser.error``. Empty listfiles
    (no inputs produced) emit a warning. Duplicate input paths (within or
    across listfiles) emit a warning but are kept.
    """
    if seen is None:
        seen = set()
    inputs: List[str] = []
    srcpaths: List[str] = []
    incpaths: List[str] = []

    for lf in listfiles:
        # realpath, not abspath: resolve symlinks so a symlinked loop
        # also trips cycle detection.
        try:
            abs_lf = os.path.realpath(lf)
        except OSError as exc:
            parser.error(f"--inputlist: cannot resolve {lf!r}: {exc}")
        if abs_lf in seen:
            parser.error(f"--inputlist: cycle detected on {lf!r}")
        seen.add(abs_lf)

        try:
            with open(lf, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError as exc:
            parser.error(f"--inputlist: cannot read {lf!r}: {exc}")

        produced_inputs = 0
        for lineno, raw in enumerate(lines, 1):
            directive, tokens = _parse_listfile_line(raw)
            if not tokens:
                continue
            if directive is None or directive == "--input":
                inputs.extend(tokens)
                produced_inputs += len(tokens)
            elif directive == "--inputlist":
                sub_in, sub_src, sub_inc = _expand_listfiles(
                    tokens, parser, seen=seen
                )
                inputs.extend(sub_in)
                srcpaths.extend(sub_src)
                incpaths.extend(sub_inc)
                produced_inputs += len(sub_in)
            elif directive == "--srcpath":
                srcpaths.extend(tokens)
            elif directive == "--includepath":
                incpaths.extend(tokens)
            else:  # pragma: no cover - guarded by directive lookup
                parser.error(
                    f"--inputlist {lf!r}:{lineno}: unknown directive {directive!r}"
                )

        if produced_inputs == 0:
            warning(f"--inputlist: {lf} contributed no inputs")

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
    if args.parse_only and args.generate_only:
        parser.error("--parse-only and --generate-only are mutually exclusive")
    if args.keep_tmp:
        args.use_tmp = True
    # -sv is shorthand for '--extension .vpy=.sv'. If the user already passed
    # an explicit .vpy mapping with a different output extension, raise; if
    # they passed exactly .vpy=.sv it's a redundant no-op.
    if args.systemverilog:
        explicit_vpy = next(
            (out for (in_ext, out) in args.extensions if in_ext == ".vpy"),
            None,
        )
        if explicit_vpy is not None and explicit_vpy != ".sv":
            parser.error(
                f"-sv requests '.vpy=.sv' but --extension .vpy={explicit_vpy} "
                f"was also given; mappings conflict."
            )
        if explicit_vpy is None:
            args.extensions.append((".vpy", ".sv"))

    if args.inputlist:
        extra_in, extra_src, extra_inc = _expand_listfiles(args.inputlist, parser)
        # -i entries first, then listfile contents in --inputlist order.
        args.input = list(args.input) + extra_in
        args.srcpath = list(args.srcpath) + extra_src
        args.includepath = list(args.includepath) + extra_inc
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
