# genesispy -- incompatibilities with genesis2

Behaviour differences between genesispy and Perl Genesis2 that affect output
or runtime semantics. Cosmetic changes from the Perl-to-Python port (`//;`
body language, `.vp`/`.svp` -> `.vpy`/`.svpy`, `.cfg` under `exec()` instead
of `eval`, GNU-style CLI flags, new flags such as `--extension`,
`--out-type`, `--synth-dir`, `--verif-dir`) are covered in the user's guide
and omitted here.

## 1. Unique-module hash is not bit-equal to Genesis2

**Where:** `hashing.py`

genesispy canonicalises the parameter dict to JSON (sorted keys, fixed encoding) and hashes it with SHA-256.
Genesis2 used Perl `Data::Dumper` output hashed with `Digest::SHA`.

The SHA-256 is used as a cache key, not as a visible name component.
Generated unique-module names differ in format between the two implementations:

- `unique_inst` (numeric style): `Foo_unq1`, `Foo_unq2`, ...
- `unique_inst_param` (param style): `Foo_KEY_VAL[_KEY_VAL...]`; non-word values use a short-digest
  pair (`KEY_<8hexchars>`); on scoped-override paths a `_unqN` counter is appended.

These differ from the Perl `Foo_<sha>` format, which propagates to filenames, instance names, and the
module list. The parity test suite handles this with a name-normaliser that maps Perl uniques to Python
uniques by structural position before diffing the emitted Verilog.

## 2. XML configs are no longer accepted by the core CLI

**Where:** `tools/xml_json.py`, `bin/genesispy-xml2json`, `bin/genesispy-json2xml`

genesispy core is JSON-only. The `--xml`/`--xmlout` CLI flags are removed; `xml_io.py` is gone. Legacy
Genesis2 XML configs convert via the standalone helpers:

```sh
genesispy-xml2json in.xml out.json
genesispy-json2xml in.json out.xml   # symmetry; lossy on plural-collapse
```

The helper preserves the explicit `force_list` set (`Parameter`, `ParameterItem`, `SubInstanceItem`,
`ArrayItem`, `HashItem`, `List`, and siblings) for XML::Simple compatibility. An XML file using a *new* plural
key not in `force_list` will translate to a scalar dict even when it appears multiple times; adding such a key
requires editing `tools/xml_json.py:DEFAULT_FORCE_LIST`.

## 3. Post-elaboration dedup collapses byte-identical uniques

**Where:** `unique_module.py:unique_inst`

genesispy collapses two `unique_inst` calls when their *resolved* parameter dicts (after `execute()` runs)
match, even if their explicit overrides differ -- e.g. `unique_inst(Foo)` and `unique_inst(Foo, N=8)` when
`Foo`'s body itself sets `parameter('N', 8)`. Perl Genesis2 had no equivalent post-elaboration dedup and
would emit both as separate unique modules even though the bodies are byte-identical.

The mechanics (two-stage pre-key/post-key cache, scoped-subtree signature, journaled rollback of the
discarded child's cache writes) live in [code-structure.md](./code-structure.md) section 5.

The parity test suite compares emitted Verilog as a *set* of files rather than a multiset, so the extra Perl
duplicates do not register as a parity failure.

## 4. `--json-out` sibling-file names

**Where:** `config_handler.py:write_json`

Perl emits `FILE`, `small_<basename>`, `tiny_<basename>` (underscore prefix). genesispy emits
`FILE`, `<stem>-small<ext>`, `<stem>-tiny<ext>` (suffix on the stem). Filenames only, with one
content difference: `ImmutableParameters` holds the force-pinned parameters, where Perl fills it by
inheritance recursion (`ConfigHandler.pm:683-708`).

## 5. Command-line overrides: bare names, unused overrides warn

**Where:** `config_handler.py:_parse_cmdln_param`, `report_unused`

- A bare `-p W=9` is accepted and applies to every instance whose body reads `W`; Genesis2
  requires `path.name` (`ConfigHandler.pm:364`). The dotted form works in both engines.
- A command-line or `.cfg` override that no instance reads is reported after elaboration as
  `warning: override NAME was never used` and the run exits 0; Genesis2's `Finalize` dies
  (`ConfigHandler.pm:436-442`). JSON parameters are not checked in either engine.

The `.cfg` API (`configure`, `get_configuration`, `exists_configuration`, `remove_configuration`)
requires `path.name`, and `get_configuration` on a name nothing set is fatal, as in Genesis2
(`ConfigHandler.pm:1349-1356, 1512`).
