# Emacs support for genesispy templates

Major mode `genesispy-mode` for Python-templated Verilog/SystemVerilog
files (`.vpy` / `.svpy` / `.gvpy`).

Derives from `verilog-mode` and uses `mmm-mode` to layer `python-mode`
onto `//;` lines and backtick expressions.

## Install

```sh
mkdir -p ~/.emacs.d/lisp/mmm
curl -sSL https://melpa.org/packages/mmm-mode-20240222.428.tar \
    | tar -x --strip-components=1 -C ~/.emacs.d/lisp/mmm
cp genesispy-mode.el ~/.emacs.d/
```

Add to `~/.emacs.d/init.el`:

```elisp
(add-to-list 'load-path "~/.emacs.d/lisp/mmm")
(require 'mmm-mode)
(load "~/.emacs.d/genesispy-mode")
(setq mmm-submode-decoration-level 0)
(setq mmm-global-mode 'maybe)
```
