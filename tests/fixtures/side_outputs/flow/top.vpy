//; register_extension('.rdlpy', '.rdl', listed=False)
//; r = generate('regs', 'u_regs')
//; text = r.get_output_text()
//; n_lines = len(text.splitlines())
//; self.write_side_file(f"{mname()}_regs.sv", f"// core\n// rdl lines: {n_lines}\n")
module `mname` ();
endmodule
