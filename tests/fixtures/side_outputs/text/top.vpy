//; a = generate('leaf', 'u_a')
//; b = generate_w_name('leaf', 'leaf_named', 'u_b')
//; c = generate('leaf', 'u_c')
//; self.texts = [x.get_output_text() for x in (a, b, c)]
module `mname` ();
    `a.instantiate()`
    `b.instantiate()`
    `c.instantiate()`
endmodule
