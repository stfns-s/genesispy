// integer logarithm base 2
//; import math, re as _re
//; h = self.include_params
//; func_name  = h.get('func_name', 'f_log2')             # name of the generated Verilog function
//; input_width = h.get('input_width', -1)          # input operand bit width
//; symmetric_input   = h.get('symmetric_input', False)                  # True: input is never -2^(w-1), so skip the most-negative remap
//; log_frac_bits   = h.get('log_frac_bits', 0)                      # extra fractional log LSBs (mantissa precision bits)
//; approx_negate = h.get('approx_negate', True)                 # True: cheap ones-complement negate; False: exact two's-complement
//; in_msb  = input_width - 1
//; log_msb = int(math.log(input_width) / math.log(2) + 1) + log_frac_bits
//; _d = getattr(self, func_name, {}); _d['out_width'] = log_msb + 1; setattr(self, func_name, _d)
//
// `func_name`(x[`input_width`:1]) ==> {sign, log(abs(x))[`log_msb-1`:1]} isym:`symmetric_input`, nlsb:`log_frac_bits`, approx:`approx_negate`
function [`log_msb`:0]  `func_name`;
input signed [`in_msb`:0] x;
integer i;
reg  signed [`in_msb`:0] ix;
reg  sign;
begin
//; if not symmetric_input:
	ix = ( x == {1'b1, {(`in_msb`){1'b0}}} ) ? {1'b1, {(`in_msb-1`) {1'b0}}, 1'b1} : x;
//; else:
	ix = x;
//; # endif
	sign = x[`in_msb`];
//; if approx_negate:
	ix = sign ? ~ix : ix;
//; else:
	ix = sign ? -ix : ix;
//; # endif

	casez ( ix[`in_msb-1`:0] )  // synthesis full_case
//; for bit in range(in_msb, 0, -1):
//;     pattern_str = '0' * (in_msb - bit) + '1' + '?' * (bit - 1)
//;     pattern_min_bits = pattern_str.replace('?', '0')
//;     log_val = int((math.log(int(pattern_min_bits, 2)) / math.log(2) + 1) * 2**log_frac_bits)
//;     if log_frac_bits == 0:
	`f"{in_msb}'b{pattern_str}"`:  `func_name` = {sign, `log_msb`'d`log_val`}; // `log_val`
//;     else:
//;         frac_lim   = log_frac_bits if bit - log_frac_bits >= 0 else bit
//;         mask   = (1 << (frac_lim + 1)) - 1
//;         base_mask   = mask
//;         lsb_index = 0 if bit - frac_lim - 1 < 0 else bit - frac_lim - 1
//;         slice_width    = (bit - 1) - lsb_index + 1
	`f"{in_msb}'b{pattern_str}"`:
		casez ( ix[`bit-1`:`lsb_index`] )
//;         for frac_step in range(1, frac_lim + 2):
//;             sub_val = mask << (bit - frac_lim)
//;             if frac_step >= 2:
//;                 sub_val = sub_val | (1 << (1 + bit - frac_lim))
//;             # endif
//;             sub_log_val = int((math.log(sub_val) / math.log(2)) * 2**log_frac_bits)
//;             mask_str  = format(mask, 'b')
//;             m    = _re.match(r'(1*0)(0*)', mask_str)
//;             if m:
//;                 mask_str = m.group(1) + m.group(2).replace('0', '?')
//;             # endif
//;             if len(mask_str) > slice_width:
//;                 mask_str = mask_str[1:]
//;             # endif
		`slice_width`'b`mask_str`: `func_name` = {sign, `log_msb`'d`sub_log_val`}; // `f"{sub_log_val / 2**log_frac_bits:.{log_frac_bits}f}"`  msk:`format(mask, 'b')`
//;             mask = (mask << 1) & base_mask
//;         # endfor
		default: `func_name` = {sign, `log_msb`'d`log_val`}; // `f"{log_val / 2**log_frac_bits:.{log_frac_bits}f}"`
		endcase
//;     # endif
//; # endfor
//; zero_pattern = f"{in_msb}'b" + format(0, f'0{in_msb}b')
	`zero_pattern`:  `func_name` = {sign, `log_msb`'d0};
	default: `func_name` = {sign, `log_msb`'d0};
	endcase

end
endfunction
