//; a = generate('leaf_plain', 'u_a')
//; b = generate('leaf_plain', 'u_b')
//; b.write_side_file('b_notes.rpt', 'notes\n', listed=False)
module `mname` ();
    `a.instantiate()`
    `b.instantiate()`
endmodule
