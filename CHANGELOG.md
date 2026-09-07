# Changelog

Notable changes to genesispy. Versions follow `pyproject.toml`.

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
