;;; genesispy-mode.el --- Major mode for genesispy .vpy/.svpy/.gvpy templates -*- lexical-binding: t; -*-

;; Keywords: languages, verilog, python
;; Package-Requires: ((emacs "26.1") (mmm-mode "0.5.9"))
;;
;; This file mirrors `extras/vim/syntax/genesispy.vim'.


(require 'verilog-mode)
(require 'mmm-mode)
(require 'mmm-auto)

(defgroup genesispy nil
  "Major mode for genesispy Python-templated Verilog files."
  :group 'languages
  :prefix "genesispy-")

(defface genesispy-delim-face
  '((t :inherit font-lock-preprocessor-face))
  "Face for the genesispy region delimiters: `//;' and the bracketing backticks."
  :group 'genesispy)

(defface genesispy-sentinel-face
  '((t :inherit font-lock-comment-face :weight bold))
  "Face for comment-only Python lines (`//; # ...' or `{% # ... %}')."
  :group 'genesispy)

(defface genesispy-j2-comment-face
  '((t :inherit font-lock-comment-face))
  "Face for Jinja2 `{# ... #}' template comments."
  :group 'genesispy)

(defconst genesispy--verilog-backtick-directives
  '("timescale" "default_nettype" "include"
    "ifdef" "if" "ifndef" "else" "endif")
  "Verilog `directive keywords excluded from inline-Python region matching.")

(defconst genesispy--font-lock-keywords
  `(("^[ \t]*//;[ \t]*#.*$" . 'genesispy-sentinel-face)
    ("//;\\(?:[^#]\\|$\\)" 0 'genesispy-delim-face t)
    ("`" . 'genesispy-delim-face)
    ;; --jinja2 delimiters. The whitespace modifiers `{%-' / `-%}'
    ;; are accepted by the parser as a syntactic no-op. The `{{ ... }}'
    ;; expression form is intentionally not highlighted -- it collides
    ;; with Verilog brace patterns (nested concatenation, replication
    ;; closes), so it is left as plain Verilog.
    ("{%-?[ \t]*#[^%]*%}" . 'genesispy-sentinel-face)
    ("{%-?\\|-?%}" . 'genesispy-delim-face)
    ("{#\\(?:.\\|\n\\)*?#}" 0 'genesispy-j2-comment-face t))
  "Additional font-lock keywords for `genesispy-mode'.")

;;;###autoload
(define-derived-mode genesispy-mode verilog-mode "Genesispy"
  "Major mode for genesispy Python-templated Verilog/SystemVerilog files."
  (font-lock-add-keywords nil genesispy--font-lock-keywords))

;;;###autoload
(progn
  (add-to-list 'auto-mode-alist '("\\.vpy\\'"  . genesispy-mode))
  (add-to-list 'auto-mode-alist '("\\.svpy\\'" . genesispy-mode))
  (add-to-list 'auto-mode-alist '("\\.gvpy\\'" . genesispy-mode)))

;; Emacs regex has no lookahead; exclusions are done via :front-verify.

(defun genesispy--python-line-verify ()
  "Return non-nil unless the matched `//;' is a `//; # ...' comment line."
  (save-excursion
    (goto-char (match-end 0))
    (not (looking-at-p "[ \t]*#"))))

(defun genesispy--j2-stmt-verify ()
  "Return non-nil unless the matched `{%' opens a `{% # ... %}' sentinel."
  (save-excursion
    (goto-char (match-end 0))
    (not (looking-at-p "-?[ \t]*#"))))

(defun genesispy--python-inline-verify ()
  "Return non-nil unless the matched backtick opens a Verilog directive."
  (save-excursion
    (goto-char (match-end 0))
    (not (looking-at-p
          (concat "\\(?:"
                  (mapconcat #'regexp-quote
                             genesispy--verilog-backtick-directives "\\|")
                  "\\)\\>")))))

(mmm-add-classes
 '((genesispy-python-line
    :submode python-mode
    :face mmm-code-submode-face
    :front "//;"
    :front-verify genesispy--python-line-verify
    :back  "$"
    :include-front nil
    :include-back nil)
   (genesispy-python-inline
    :submode python-mode
    :face mmm-code-submode-face
    :front "\\(?:^\\|[^\\\\]\\)\\(`\\)"
    :front-match 1
    :front-verify genesispy--python-inline-verify
    :back  "\\(?:^\\|[^\\\\]\\)\\(`\\)"
    :back-match 1
    :include-front nil
    :include-back nil)
   (genesispy-j2-stmt
    :submode python-mode
    :face mmm-code-submode-face
    :front "{%-?"
    :front-verify genesispy--j2-stmt-verify
    :back  "-?%}"
    :include-front nil
    :include-back nil)))

(mmm-add-mode-ext-class 'genesispy-mode nil 'genesispy-python-line)
(mmm-add-mode-ext-class 'genesispy-mode nil 'genesispy-python-inline)
(mmm-add-mode-ext-class 'genesispy-mode nil 'genesispy-j2-stmt)

(provide 'genesispy-mode)

;;; genesispy-mode.el ends here
