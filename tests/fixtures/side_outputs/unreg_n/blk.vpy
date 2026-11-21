//; N = parameter('N', 2)
//; cell = generate_w_name('cell', f"{mname()}_cell", 'u_cell', W=N)
module `mname` ();
  `cell.instantiate()` ();
endmodule
