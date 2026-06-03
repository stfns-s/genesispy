# genesispy

Python port of the Genesis2 Chip Generator (see
<https://github.com/StanfordVLSI/Genesis2>). Replaces the Perl runtime
with a pure-Python implementation while keeping the template hierarchy
(now `.vpy` / `.svpy`). Configuration is JSON; legacy Genesis2 `.xml`
configs convert via the bundled `genesispy-xml2json` helper.

## Install

### Without pip (recommended -- `bin/` launchers)

The repo ships shell launchers in `bin/` (`bin/genesispy`, `bin/gvpy`)
that set `PYTHONPATH` to the sibling `src/` and exec
`python3 -m genesispy.cli`. No build step, no pip -- just run from a
checkout:

```sh
./bin/genesispy --input top.vpy --top top --json config.json
```

To "install" to a destination, copy `bin/` and `src/` together (the
launchers resolve `src/` as `../src` relative to their own directory):

```sh
DEST=/path/to/install-dir
mkdir -p "$DEST"
cp -a bin src "$DEST/"
export PATH="$DEST/bin:$PATH"
```

### With pip

```sh
pip install -e .
# or
pip install --target /path/to/install-dir .
```

## Tests

After `pip install -e .`:

```sh
pytest tests/
```

Without installing -- use the in-tree source via `PYTHONPATH`:

```sh
PYTHONPATH=src pytest tests/
```

## Documentation

- [doc/user-guide.md](./doc/user-guide.md) -- `.vpy` syntax, walkthrough,
  CLI reference for `genesispy` and `gvpy`, migrating from Genesis2.
- [doc/code-structure.md](./doc/code-structure.md) -- pipeline, dedup,
  control flags.
- [doc/interfaces.md](./doc/interfaces.md) -- module-boundary
  interfaces.
- [doc/genesis2-incompatibilities.md](./doc/genesis2-incompatibilities.md)
  -- non-obvious behavior differences from Perl Genesis2.
