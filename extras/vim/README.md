# Vim support for genesispy templates

Filetype detection and syntax highlighting for Python-templated Verilog
files (`.vpy` / `.svpy` / `.gvpy`).

Highlights:
- Verilog (or SystemVerilog if `syntax/verilog_systemverilog.vim` is on the
  runtime path) as the base.
- `//;`-prefixed embedded-language lines highlighted via `@pythonTop`.
- Backtick-delimited inline expressions, escape-aware (`` \` ``) and
  excluding Verilog backtick directives (`` `timescale ``, `` `ifdef ``, ...).
- Comment-only embedded lines (`//; # ...`) highlighted bold so block-closing
  sentinels (`# endfor`, `# endif`, ...) stand out from regular statements.

## Install

### Manual

Copy (or symlink) both files into your vim runtime:

```sh
mkdir -p ~/.vim/ftdetect ~/.vim/syntax
cp ftdetect/genesispy.vim ~/.vim/ftdetect/genesispy.vim
cp syntax/genesispy.vim   ~/.vim/syntax/genesispy.vim
```

For Neovim, swap `~/.vim` for `~/.config/nvim`.

### Plugin manager

Point your manager at this subdirectory. With `vim-plug`:

```vim
Plug 'youruser/genesispy-port', { 'rtp': 'genesispy/extras/vim' }
```

(Adjust the source spec for your fork/clone location.)

## Files

- `ftdetect/genesispy.vim` -- maps `*.vpy`, `*.svpy`, `*.gvpy` to filetype
  `genesispy`.
- `syntax/genesispy.vim` -- Python-embedded syntax rules layered on top of
  Verilog/SystemVerilog.
