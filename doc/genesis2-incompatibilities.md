# genesispy -- incompatibilities with genesis2

This document lists the subtle, behavior-affecting differences between genesispy and Perl Genesis2.
Superficial changes that follow inevitably from a Perl-to-Python port (`//;` body language, `.vp`/`.svp` ->
`.vpy`/`.svpy`, `.cfg` running under trusted-input `exec()` instead of `eval`, GNU-style CLI flags, new flags such
as `--suffix`, `--out-type`, `--synth-dir`, `--verif-dir`) are covered in the user's guide and omitted here.

The items below are the ones a porting user is most likely to encounter.

## 1. Unique-module hash is not bit-equal to Genesis2

**Where:** `hashing.py`

genesispy canonicalises the parameter dict to JSON (sorted keys, fixed encoding) and hashes it with SHA-256.
Genesis2 used Perl `Data::Dumper` output hashed with `Digest::SHA`.

The hashes are stable across Python runs and across hosts, but they are **not bit-equal** to the Perl ones.
Generated unique-module names (`Foo_<hash>`) therefore differ digit-for-digit between the two implementations,
which propagates to filenames, instance names, and the module list. The parity test suite handles this with a
name-normaliser that maps Perl uniques to Python uniques by structural position before diffing the emitted
Verilog.

## 2. XML configs are no longer accepted by the core CLI

**Where:** `tools/xml_json.py`, `bin/genesispy-xml2json`, `bin/genesispy-json2xml`

genesispy core is JSON-only. The `--xml`/`--xmlout` CLI flags are removed; `xml_io.py` is gone. Legacy
Genesis2 XML configs convert via the standalone helpers:

```
genesispy-xml2json in.xml out.json
genesispy-json2xml in.json out.xml   # symmetry; lossy on plural-collapse
```

The helper preserves the explicit `force_list` set (`Parameter`, `ParameterItem`, `SubInstanceItem`,
`ArrayItem`, `HashItem`, `List`, and siblings) for XML::Simple compatibility. An XML file using a *new* plural
key not in `force_list` will translate to a scalar dict even when it appears multiple times; adding such a key
requires editing `tools/xml_json.py:DEFAULT_FORCE_LIST`.

## 3. Post-elaboration dedup collapses byte-identical uniques

**Where:** `unique_module.py:unique_inst`

genesispy uses a two-stage cache: a *pre-key* hashed from the explicit overrides supplied to `unique_inst`
(fast path, avoids re-running `execute()`), and a *post-key* hashed from the fully resolved parameter dict
*after* `execute()` has run.

The post-key catches the case where two calls with different explicit-override sets nevertheless converge to
the same final parameter state -- for example `unique_inst(Foo)` and `unique_inst(Foo, N=8)` collapse if
`Foo`'s body sets `parameter('N', 8)` itself. Perl Genesis2 had no equivalent post-elaboration dedup and would
emit both as separate unique modules even though the bodies are byte-identical.

The parity test suite compares emitted Verilog as a *set* of files rather than a multiset, so the extra Perl
duplicates do not register as a parity failure.

## 4. `--json-out` sibling-file names

**Where:** `config_handler.py:write_json`

Perl Genesis2 `-hierarchy FILE` writes `FILE`, `small_<basename(FILE)>`, and `tiny_<basename(FILE)>` --
underscore-prefixed siblings. genesispy `--json-out FILE` instead splits the basename with `os.path.splitext`
and writes `FILE`, `<stem>-small<ext>`, and `<stem>-tiny<ext>`. For example, `--json-out hier.json` produces
`hier.json`, `hier-small.json`, `hier-tiny.json`. The content of each variant is unchanged; only the filenames
differ.

