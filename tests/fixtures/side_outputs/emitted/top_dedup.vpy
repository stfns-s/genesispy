//; a = generate('leaf', 'u0')
//; b = generate('leaf', 'u1')
//; self.result = (b._clone_of is a, b.get_emitted_text(), a.get_output_text())
module `mname` ();
    `a.instantiate()`
    `b.instantiate()`
endmodule
