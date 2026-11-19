# Changelog

Notable changes to genesispy. Versions follow `pyproject.toml`.

## 0.6.4

- Incompatible: the `--param-footer` header reads "Genesis-Py resolved parameter sources:", and
  the `--defaults` source is labelled `defaults file (--defaults)`.
- `--param-footer`: a forced parameter names the source of its input after a second `<-`.
- `--json-out`: forced items carry `InputSource`, the source of the value the force replaced.
  `genesispy-json2xml` drops it, since Genesis2 rejects an unknown key in a parameter item.
- New `--ignore-unused KIND[,KIND...]`: listed unused kinds are dropped without a message; a kind
  also in `--strict-unused` stays an error.
- New `form=` on `verilog.sext` and `verilog.pad_low`: `cast` emits a size cast with a signing
  cast, `concat` (default) the 0.6.3 text. The default is set by `verilog.set_widen_form()` or
  `--verilog-default-widen-form`; a `set_widen_form()` call during elaboration warns, in genesispy
  and gvpy.
- New `fmt=` on `verilog.lit`: `"bin"` or `"hex"` writes the two's-complement digits, `8'sb11111011`
  or `8'shfb`, exact in any context width; `None` (default) and `"dec"` keep the decimal text.
- New `verilog.limit(bound, width, signed=True, symm=False, fmt="bin")`: the min or max end of a
  format as a sized literal, `8'sb10000000`; `symm` raises the min end by one.
- dsp demo: updated to showcase the new features of `genesispy.lib.verilog`.

## 0.6.3

- Incompatible: `--json-out` puts parent-keyword parameters under `ImmutableParameters`, as Perl
  does; `tiny` keeps only `--json-cfg` and `--parameter` values.
- Incompatible: `ConfigHandler.report_unused` returns `(kind, message)` pairs.
- A `--defaults` key counts as used whenever `parameter()` names it, whichever source wins. A key
  for a forced parameter warns `default ENTRY.KEY is forced`.
- New `--strict-unused KIND[,KIND...]`: listed unused kinds are errors, exit 3, no output.
- New `--defaults-entry NAME`: the top reads entry `NAME` before its own.
- New `--top-name NAME`: emit the `--top` template as NAME, as `generate_w_name` does.
- `--json-out` nodes carry `TemplateName`; `--json-cfg` ignores it.
- `genesispy-json2xml` writes a config Genesis2 reads: item wrappers restored, list and dict values
  typed, booleans as `true`/`false`.
- Demo makefiles (`genesispy.mk`, dsp, gvpy): a changed command line always rebuilds. The stamp is
  checked at makefile read time and written with `$(file)`; needs GNU make 4.2.

## 0.6.2

- Incompatible: a bare `-p NAME=VALUE` needs `--params-global`, as in Genesis2. gvpy is exempt.
- New `--defaults FILE` (genesispy and gvpy): per-module parameter defaults, below `.cfg`.
- New `genesispy.lib.verilog`: Verilog text from Python values; the bare name `verilog` in
  templates. Replaces the dsp demo's `lib/vexpr.py`.
- dsp demo: `sym`/`osym`/`OSYM`/`ISYM` names become `symm`/`osymm`/`OSYMM`/`ISYMM`; `qfmt`'s
  `clamp=` becomes `saturate=`.
- A long parameter value wraps across comment lines; output with list or dict parameters differs.

## 0.6.1

Findings of the 2026-09 code review.

Genesis2 divergences removed:

- Parser: backslash runs on a backtick line collapse to one.
- Listfiles: an undefined variable or missing path is dropped with a warning.
- A string-named `unique_inst` searches the invocation directory and `--src-path`, not
  `--inc-path`.
- `genesispy-xml2json` types a value only when lossless; the JSON loader no longer coerces strings.
- `get_module_name()` returns the unique name; new `get_base_name()`; `get_instance_path()` is
  dot-joined.
- `.cfg` takes `path.name` only; `get_configuration` on an unset name is a `ConfigError`.
- Parameters lock once the body has run; a late write, a second declaration or a second force is
  fatal.
- A changed command line removes the product before the rebuild.

Other:

- Configuration: JSON parameters resolve by instance path and enter the dedup key; the schema is
  validated; unused overrides warn; JSON `null` overrides to `None`.
- `genesispy-vp2vpy`: more Perl constructs translate; every unrecognised one reaches `--strict`.
- Parser: multi-line `//;` keeps its indent; `` \` `` escapes inside expressions.
- Names: colliding template stems, keyword stems and non-`\w+` parameter names are errors.
- gvpy: a body's `synonym()` resolves in a later `generate()`.
- Command line: one-line error reports; `--clean` removes every product; no inputs is an error.
- Engine: `--no-module-cache` also bypasses the `ununique_inst` registry.
- Build: `make gen` reaches a steady state; the `%.json: %.xml` rule is gone.
- Docs: deprecated aliases (user guide 9.5), JSON schema (6.3), `doc/genesis2-incompatibilities.md`.
- Tests and CI: one cache reset, shared staging helpers, a real-`Manager` test per flag, ruff in CI.

## 0.6.0

- New `pyinclude()`: exec a raw `.py` into the caller's namespace (`pinclude` deprecated).
- The dsp demo, formerly the `dsp-gpy` submodule, is vendored in.

## 0.2.1

- `--jinja2` renamed to `--j2`, no alias.
