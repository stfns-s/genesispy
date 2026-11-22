//; src = unique_inst('leaf', 'u0')
//; cl = clone_inst(src, 'u1')
//; self.result = (cl.get_emitted_text(clone='source'), src.get_output_text())
module `mname` ();
    `src.instantiate()`
endmodule
