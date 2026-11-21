//; N = parameter('N', 2)
//; self.write_side_file(f"{mname()}.rpt", f"N={N}\n")
//; cell = generate_w_name('cell', f"{mname()}_cell", 'u_cell', W=8)
module `mname` ();
  `cell.instantiate()` ();
endmodule
