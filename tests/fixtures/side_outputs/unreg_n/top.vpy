//; a = generate('blk', 'u_a')
//; b = generate('blk', 'u_b', N=2)
//; c = generate('blk', 'u_c', N=3)
module `mname` ();
  `a.instantiate()` ();
  `b.instantiate()` ();
  `c.instantiate()` ();
endmodule
