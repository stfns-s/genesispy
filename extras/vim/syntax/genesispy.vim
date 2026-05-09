" Vim syntax file
" Language: genesispy Python template (.vpy / .svpy / .gvpy)
" Embedded Python via @pythonTop, with escape-aware backticks and
" Verilog-directive exclusion. Also covers --jinja2 statement and
" comment delimiters ({% ... %}, {# ... #}) since the engine is
" per-run and the same source file can be elaborated either way.
" The `{{ ... }}` expression form is intentionally NOT highlighted
" -- it collides with Verilog brace patterns (nested concatenation,
" replication closes); leaving it as plain Verilog avoids false
" regions in non-jinja2 sources.

if version < 600
    syntax clear
elseif exists("b:current_syntax")
    finish
endif

" Base: SystemVerilog if available, else plain Verilog.
if !empty(globpath(&runtimepath, 'syntax/verilog_systemverilog.vim'))
    ru! syntax/verilog_systemverilog.vim
    set ft=verilog_systemverilog
else
    ru! syntax/verilog.vim
    set ft=verilog
endif
unlet! b:current_syntax

" Embedded Python.
syn include @pythonTop syntax/python.vim

" //; # ... -- comment-only Python lines (block-closing sentinels like
" `# end if`, `# endif`, `# end for`, `# endfor`). Highlighted as comments
" but bold so they stand out as structural markers.
syn match genesispySentinel +//;\s*#.*$+ containedin=ALL

" //;<rest> -- the rest of the line is Python (excluding the sentinel form
" above, which is matched separately).
syn region genesispyLine matchgroup=genesispyDelim
    \ start=+//;\(\s*#\)\@!+ end=+$+
    \ keepend containedin=ALL contains=@pythonTop

" `expr` -- inline Python expression.
"   * \\\@<! is "not preceded by a backslash" so the gvpy literal-backtick
"     escape (\`) does not open or close the region.
"   * \@! after the start backtick excludes the Verilog `directive keywords
"     so they are not mis-parsed as opening a Python region.
syn region genesispyInline matchgroup=genesispyDelim
    \ start=#\\\@<!`\(timescale\|default_nettype\|include\|ifdef\|if\|ifndef\|else\|endif\)\@!#
    \ end=#\\\@<!`#
    \ keepend containedin=ALL contains=@pythonTop oneline

" --jinja2 delimiters. Whitespace modifiers `{%-`, `-%}` are accepted
" as a syntactic no-op. Either form may span multiple physical lines,
" so no `oneline`.
"
" Sentinel form: `{% # endfor %}` (and friends) -- highlight as a
" structural comment, like `//; # ...`.
syn match genesispyJ2Sentinel +{%-\?\s*#[^%]*%}+ containedin=ALL

" {% python stmt %} -- excludes the sentinel form above.
syn region genesispyJ2Stmt matchgroup=genesispyDelim
    \ start=+{%-\?\(\s*#\)\@!+ end=+-\?%}+
    \ keepend containedin=ALL contains=@pythonTop

" {# template comment #} -- stripped at elaboration; pure comment.
syn region genesispyJ2Comment matchgroup=genesispyDelim
    \ start=+{#+ end=+#}+ keepend containedin=ALL

hi link genesispyJ2Comment Comment
hi link genesispyDelim PreProc

" Make embedded Python visually distinct from Verilog (which uses Statement).
hi genesispyPyKeyword  cterm=bold gui=bold ctermfg=magenta guifg=magenta
hi genesispyPyBuiltin  cterm=bold gui=bold
hi genesispyPyFunction cterm=bold gui=bold
hi link pythonStatement   genesispyPyKeyword
hi link pythonConditional genesispyPyKeyword
hi link pythonRepeat      genesispyPyKeyword
hi link pythonOperator    genesispyPyKeyword
hi link pythonException   genesispyPyKeyword
hi link pythonInclude     genesispyPyKeyword
hi link pythonBuiltin     genesispyPyBuiltin
hi link pythonFunction    genesispyPyFunction
hi link pythonDecorator   genesispyPyKeyword

" Sentinel highlight: same foreground as Comment, but bold. We can't use
" `:hi link` (it would clobber the bold attribute), so resolve Comment's
" colours at load time and apply them explicitly.
let s:_cterm_fg = synIDattr(synIDtrans(hlID('Comment')), 'fg', 'cterm')
let s:_gui_fg   = synIDattr(synIDtrans(hlID('Comment')), 'fg', 'gui')
exe 'hi genesispySentinel cterm=bold gui=bold'
    \ . (!empty(s:_cterm_fg) ? ' ctermfg=' . s:_cterm_fg : '')
    \ . (!empty(s:_gui_fg)   ? ' guifg='   . s:_gui_fg   : '')
exe 'hi genesispyJ2Sentinel cterm=bold gui=bold'
    \ . (!empty(s:_cterm_fg) ? ' ctermfg=' . s:_cterm_fg : '')
    \ . (!empty(s:_gui_fg)   ? ' guifg='   . s:_gui_fg   : '')
unlet s:_cterm_fg s:_gui_fg

let b:current_syntax = "genesispy"

" vim: set ts=4 sw=4:
