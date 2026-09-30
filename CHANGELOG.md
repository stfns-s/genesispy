# Changelog

Notable changes to genesispy. Versions follow `pyproject.toml`.

## 0.6.3

- Incompatible: `--json-out` files parameters as Perl does. A parameter a parent keyword set now
  goes under `ImmutableParameters` with the forced ones, so it leaves full `Parameters` and the small
  variant. `tiny` keeps only parameters set by `--json-cfg` or `--parameter`, dropping parent-keyword
  and forced ones. Fed back with `--json-cfg`, a snapshot gives the same result as before.
- Incompatible: `ConfigHandler.report_unused` returns `(kind, message)` pairs.
- `--defaults` keys count as used whenever `parameter()` names them, whichever source supplies the
  value. A key outranked by a parent keyword, `-p`, `.cfg`, JSON or an earlier entry no longer
  warns; a key naming a `force=True` parameter now warns `default ENTRY.KEY is forced`.
- New `--strict-unused KIND[,KIND...]` (`overrides`, `entries`, `keys`, `all`): report those
  unused items as errors and exit 3 before writing output. User guide section 6.5.
- New `--defaults-entry NAME`: the top reads `--defaults` entry `NAME` before its own. User guide
  section 6.5.
- `--json-out` nodes carry `TemplateName`, the source template; `--json-cfg` ignores it.
- `genesispy-json2xml` output is now a Genesis2 config: it restores the `ParameterItem`,
  `SubInstanceItem` and `List` wrappers, writes a list or dict `Val` as `ArrayType`/`HashType`,
  writes booleans as `true`/`false`, and writes a dict nested in a list or hash as `HashType`. A
  `--json-out` snapshot converted this way drives Genesis2 to the same Verilog, up to unique module
  names.
- `genesispy.mk` and the dsp demo's `Makefile`: a changed command line now always rebuilds. The
  `.flags` stamp is compared, and the product removed, while make reads the makefile. Before, a
  stamp recipe removed the product after make had already read its mtime, so a stamp whose coarse
  mtime tied with the product's left the old build in place, the product deleted, and exit 0. Only
  goals that build the product do this, and not under `make -n`.

## 0.6.2

- Incompatible: a bare `-p NAME=VALUE` (no instance path) is an error unless `--params-global` is
  given, as in Genesis2; with the flag it applies to every instance that reads `NAME`, as before.
  Scripts that pass bare `-p` to genesispy must add the flag. gvpy accepts bare `-p` without it.
  The dsp demo's `Makefile` and `verif/run-tb.sh` pass the flag.
- New `--defaults FILE` (genesispy and gvpy, repeatable): per-module parameter defaults from a
  `.py` file's `BLOCK_PARAMS` dict or a `.json` file with the same tree. A module reads its own
  entry, then its source template's; the tier sits below `.cfg`, so every other source outranks
  it. Unused entries and keys are warnings. User guide section 6.5.
- New `genesispy.lib.verilog`: Verilog text from Python values (`lit`, `sext`, `pad_low`, `decl`,
  `port_map`, `idx`, `wrap_sum`, `parenthesize`). It is the dsp demo's former `lib/vexpr.py`,
  renamed, with `VExprError` now `VerilogError`, and extended with `port_map`, `wrap_sum` and a
  `col` argument to `decl`. Templates, `include()` snippets and `pyinclude`'d files see it as the
  bare name `verilog`; generated modules import it as a global. User guide section 11.7.
- dsp demo: `lib/vexpr.py` removed, the templates import `genesispy.lib.verilog`. `lib/qfmt.py`
  updated: keywords `sym`/`bsym`/`osym` of `mult`, `Bounds.of` and `requant` are now
  `symm`/`bsymm`/`osymm`, `Requant.apply(clamp=)` is `apply(saturate=)`, `round_consts` is public,
  `requant` takes `container=`, and `osymm` with an unsigned target is an error. `f_sym` is
  renamed `f_symm`; the parameters `OSYM`/`ISYM` and the include keys `osym`/`isym` are renamed
  `OSYMM`/`ISYMM` and `osymm`/`isymm`. `tb_spec_mux` declares `rnd` and `seed` before the task
  that uses them, which current iverilog requires.
- Comments: a parameter value too wide for one line now wraps across several,
  continuations hanging under the value column, in both the `to_verilog`
  banner and the `--param-footer` provenance block. Lines are budgeted to 100
  columns including the comment prefix. Sequences fill; a dict renders one key
  per line and a long string still runs over. Previously generated output
  differs wherever a module carries a list or dict parameter.

## 0.6.1

Findings of the 2026-09 code review, by area.

Genesis2 divergences removed (former sections of `doc/genesis2-incompatibilities.md`):

- Parser: on a line that contains a backtick, a run of backslashes collapses
  to one backslash, as in Genesis2 (Manager.pm:865-869).
- Command line: a listfile directive argument that names an undefined
  variable or a path that does not exist is dropped with a warning; a bare
  path line is kept as written (Manager.pm:614-650, 686-690).
- Module lookup: a string-named `unique_inst("leaf")` for a template not on
  `--input` is searched under the invocation directory and `--src-path`;
  `--inc-path` serves `include()` only (UniqueModule.pm:3210-3230).
- Scalars: `genesispy-xml2json` types an XML value only when that is
  lossless (`8`, `1.5`, `true`); `010` and `1e3` stay strings. The JSON
  loader no longer coerces string leaves. `-p` values are coerced as before.
- Names: `get_module_name()` returns the unique module name and the new
  `get_base_name()` the template name; `get_instance_path()` is dot-joined
  from the top's instance name, the form `get_instance_obj` takes
  (UniqueModule.pm:363-372, 1057-1081).
- Configuration: the `.cfg` API takes `path.name` only and
  `get_configuration` on an unset name is a `ConfigError`, as in Genesis2
  (ConfigHandler.pm:1349-1356, 1512); the bare form stays on the command
  line. The wallace demo's `config.py` names its instances.
- Parameters lock once the body has run: a write on an elaborated
  instance, on a clone, or on the parent while a child elaborates is fatal;
  a second declaration of a name, a second force, and `get_param` on a name
  only a parent's keyword set are fatal; undeclared keywords are warned
  about when the body finishes (UniqueModule.pm:833, 1246, 2183, 2296, 2443).
- Build: a changed command line removes the product before the rebuild, so
  a stamp that receives the same coarse mtime as the product cannot leave
  the old product up to date (`genesispy.mk`, gvpy and dsp Makefiles).

- Configuration: JSON `Parameters` resolve by instance path (root node when
  no path); `.cfg` scoped overrides and JSON values enter the dedup key; the
  JSON schema is validated on load; `Val` is accepted as a value key so
  `--json-out` output can be fed back; an unused `--parameter` or
  `configure()` override is warned about after elaboration; `--json-out`
  full carries declared defaults and puts force-pinned parameters under
  `ImmutableParameters`; an explicit JSON `null` overrides to `None`.
- Translator (`genesispy-vp2vpy`): every unrecognised construct reaches the
  TODO / `--strict` path; bare `my $x;`, `print STDERR`, `join`, `sort`,
  `reverse`, `substr`, string concatenation, `<=>`/`cmp`, `||=`/`&&=`/`//=`,
  `%hash` / `@array` call arguments and `List::Util::max/min/sum` translate;
  `sprintf` goes through a Perl-tolerant helper; the invented `/*; ;*/`
  block form is gone; a dead helper pipe is a `HelperError`; every Genesis2
  demo translation elaborates under test.
- Parser: a multi-line `//;` statement keeps the emit indent of its first
  line; a whitespace-only `//;` is a blank line; `` \` `` escapes a backtick
  inside an expression too.
- Names: two templates whose stems sanitise to one module name, and a
  keyword stem, are errors; parameter names must match `\w+`; a `synonym`
  target that names an existing template is refused.
- gvpy: a `synonym()` registered in a body resolves in a later
  string-named `generate()`; file search and `synonym_class` rules are the
  ones `Manager` uses.
- Command line: missing absolute paths, `Manager` construction faults,
  listfile quoting faults and `.cfg` runtime errors report one line
  (`.cfg` errors with `file:line`); `--clean` removes every named product;
  no inputs is an error; listfile paths resolve against the listfile's
  directory with `$VAR` expansion; `clone_inst` takes an instance path;
  `genesispy-jinja2j2` and `genesispy-xml2json` fault paths report
  cleanly; the six `bin/` launchers share one body and honour `PYTHON`.
- Engine: `--no-module-cache` also bypasses the `ununique_inst` registry;
  object-valued parameters cannot hash equal to a string parameter;
  `cache.clear_all` also resets the log tee.
- Build: `make gen` reaches a steady state after a flag change and rebuilds
  after a lazily loaded module changes; a failed gvpy run leaves no
  truncated output; `cleangen` honours `OUTPUTDIR`; the `%.json: %.xml`
  rule is gone (convert once with `genesispy-xml2json`).
- Demos: dsp functions reject a zero input width; the ported demos declare
  the Perl range constraints; regfile's `cfg_ifc` uses `parameter()`.
- Documentation: the deprecated command-line aliases are listed (user guide
  9.5); the JSON schema is specified (6.3); every remaining divergence from
  Genesis2 is in `doc/genesis2-incompatibilities.md`.
- Tests and CI: one autouse cache reset; shared stale-artefact list and
  parity helpers; every flag has a real-`Manager` test; the guide's
  `verilog` examples parse under test; `ruff.toml` is committed and CI
  lints; CI installs PPI so the translator tests run.

## 0.6.0

`pyinclude()`: exec a raw `.py` into the calling module's namespace
(`pinclude` is the deprecated spelling). The `dsp` demo vendored in from the
former `dsp-gpy` submodule.

## 0.2.1

`--jinja2` renamed to `--j2` (no alias).
