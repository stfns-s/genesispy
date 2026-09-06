//; # An include()'d snippet, so this body runs in its OWN namespace. The
//; # pyinclude below therefore lands here, not in the caller: top.vpy cannot
//; # see acc_width afterwards, which is what its "leaked into top" line shows.
//; pyinclude("fixed.py")
//; h         = self.include_params
//; func_name = h['func_name']
//; term_w    = h['term_w']
//; nterms    = h['nterms']
//; acc_w     = acc_width(term_w, nterms)
//; lo, hi    = sat_bounds(acc_w)
   // `func_name`(): headroom in bits between one term and the accumulator
   function integer `func_name`;
      input dummy;
      begin
         `func_name` = `acc_w - term_w`;
      end
   endfunction
//; # Report to the caller under the name of what was emitted, the include()
//; # convention: a snippet's own bindings do not come back.
//; _d = getattr(self, func_name, {})
//; _d.update({'acc_w': acc_w, 'lo': lo, 'hi': hi, 'headroom': acc_w - term_w})
//; setattr(self, func_name, _d)
