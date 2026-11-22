//; src = unique_inst('leaf', 'u0')
//; cl = clone_inst(src, 'u1')
//; self.result = cl.get_emitted_text(clone='empty')
module `mname` ();
    `src.instantiate()`
endmodule
