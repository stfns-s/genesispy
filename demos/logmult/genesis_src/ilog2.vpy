// integer logarithm base 2
//; import math
//; h               = self.include_params
//; func_name       = h.get('func_name', 'f_log2')
//; input_width     = h.get('input_width', -1)
//; symmetric_input = h.get('symmetric_input', False)
//; log_frac_bits   = h.get('log_frac_bits', 0)
//; approx_negate   = h.get('approx_negate', True)
//; in_msb          = input_width - 1
//; log_msb         = int(math.log(input_width) / math.log(2) + 1) + log_frac_bits
//; lscale          = 1 << log_frac_bits
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
//; # One arm per bucket: the leading one, then the log_frac_bits bits below it.
//; # val is floor(2**log_frac_bits * log2(2 * P)), P being abs(x) truncated to
//; # those bits, so a power of two reports one above its exponent -- the offset
//; # logmult.vpy and slogmult.vpy are built around.  The integer bit_length form
//; # is exact; math.log rounds the wrong way at bucket boundaries.
//; for bit in range(in_msb, 0, -1):
//;     nsub = log_frac_bits if log_frac_bits < bit - 1 else bit - 1
//;     for sub in range(1 << nsub):
//;         pat = '0' * (in_msb - bit) + '1' + (format(sub, f'0{nsub}b') if nsub else '') + '?' * (bit - 1 - nsub)
//;         pfx = ((1 << nsub) | sub) << (log_frac_bits - nsub)
//;         val = (pfx ** lscale).bit_length() - 1 + lscale * (bit - log_frac_bits)
	`f"{in_msb}'b{pat}"`:  `func_name` = {sign, `log_msb`'d`val`}; // `f"{val / lscale:.{log_frac_bits}f}"`
//;     # endfor
//; # endfor
//; zero_pattern = f"{in_msb}'b" + format(0, f'0{in_msb}b')
	`zero_pattern`:  `func_name` = {sign, `log_msb`'d0};
	default: `func_name` = {sign, `log_msb`'d0};
	endcase

end
endfunction
