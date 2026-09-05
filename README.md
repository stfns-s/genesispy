# genesispy

Python port of the Genesis2 Chip Generator (see
<https://github.com/StanfordVLSI/Genesis2>). Replaces the Perl runtime
with a pure-Python implementation while keeping the template hierarchy
(now `.vpy` / `.svpy`). Configuration is JSON; legacy Genesis2 `.xml`
configs convert via the bundled `genesispy-xml2json` helper.

## Editor support

Filetype detection and syntax highlighting for `.vpy` / `.svpy` / `.gvpy` files is available from the
[genesis-editors](https://github.com/stfns-s/genesis-editors.git) repository (Vim/Neovim, Emacs, VS
Code). Install each per its own README.

## Install

### From PyPI

```sh
pip install genesispy
```

Installs the `genesispy`, `gvpy`, `genesispy-vp2vpy`, `genesispy-xml2json`,
`genesispy-json2xml` and `genesispy-jinja2j2` commands. There are no
mandatory dependencies; three optional extras:

```sh
pip install 'genesispy[xml]'        # lxml: pretty-printed genesispy-json2xml
pip install 'genesispy[color]'      # colorama: coloured diagnostics
pip install 'genesispy[import-j2]'  # jinja2: required by genesispy-jinja2j2
```

### From a checkout, without pip (recommended for developers -- `bin/` launchers)

The repo ships shell launchers in `bin/` (`bin/genesispy`, `bin/gvpy`)
that set `PYTHONPATH` to the sibling `src/` and exec
`python3 -m genesispy.cli`. No build step, no pip -- just run from a
checkout:

```sh
./bin/genesispy --input top.vpy --top top --json-cfg config.json
```

To "install" to a destination, copy `bin/` and `src/` together (the
launchers resolve `src/` as `../src` relative to their own directory):

```sh
DEST=/path/to/install-dir
mkdir -p "$DEST"
cp -a bin src "$DEST/"
export PATH="$DEST/bin:$PATH"
```

### From a checkout, with pip

```sh
pip install -e .
# or
pip install --target /path/to/install-dir .
```

## Tests

Against the in-tree source, no install required:

```sh
PYTHONPATH=src pytest tests/
```

Against an installed copy (`pip install -e .` or `pip install genesispy`):

```sh
pytest tests/
```

## Documentation

Each entry links to the rendered copy on GitHub; the `local` link resolves in a
source checkout.

- [doc/user-guide.md](https://github.com/stfns-s/genesispy/blob/main/doc/user-guide.md)
  ([local](./doc/user-guide.md)) -- `.vpy` syntax, walkthrough, CLI reference
  for `genesispy` and `gvpy`, migrating from Genesis2.
- [doc/code-structure.md](https://github.com/stfns-s/genesispy/blob/main/doc/code-structure.md)
  ([local](./doc/code-structure.md)) -- pipeline, dedup, control flags.
- [doc/interfaces.md](https://github.com/stfns-s/genesispy/blob/main/doc/interfaces.md)
  ([local](./doc/interfaces.md)) -- module-boundary interfaces.
- [doc/genesis2-incompatibilities.md](https://github.com/stfns-s/genesispy/blob/main/doc/genesis2-incompatibilities.md)
  ([local](./doc/genesis2-incompatibilities.md)) -- non-obvious behavior
  differences from Perl Genesis2.
