//; src = unique_inst('leaf', 'u0')
//; cl = clone_inst(src, 'u1')
//; self.result = (cl.get_emitted_text(), src.get_output_text())
module `mname` ();
    `src.instantiate()`
endmodule
