//; a = generate('leaf_plain', 'u_a')
//; a.synonym('leaf_alias')
//; self.write_side_file('leaf_alias.v', 'clash\n')
module `mname` ();
    `a.instantiate()`
endmodule
