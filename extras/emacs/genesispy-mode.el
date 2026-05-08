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
  "Face for comment-only Python lines (`//; # ...')."
  :group 'genesispy)

(defconst genesispy--verilog-backtick-directives
  '("timescale" "default_nettype" "include"
    "ifdef" "if" "ifndef" "else" "endif")
  "Verilog `directive keywords excluded from inline-Python region matching.")

(defconst genesispy--font-lock-keywords
  `(("^[ \t]*//;[ \t]*#.*$" . 'genesispy-sentinel-face)
    ("//;\\(?:[^#]\\|$\\)" 0 'genesispy-delim-face t)
    ("`" . 'genesispy-delim-face))
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
    :include-back nil)))

(mmm-add-mode-ext-class 'genesispy-mode nil 'genesispy-python-line)
(mmm-add-mode-ext-class 'genesispy-mode nil 'genesispy-python-inline)

(provide 'genesispy-mode)

;;; genesispy-mode.el ends here
