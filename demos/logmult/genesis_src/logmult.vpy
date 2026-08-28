// signed log multiplier - a*b =~ antilog(log2(a)+log2(b)), optional final shift/antilog
//; import math
//; h                    = self.include_params
//; func_name            = h.get('func_name', 'f_logmult')
//; sign_only            = h.get('sign_only', False)
//; a_width              = h['a_width']
//; b_width              = h['b_width']
//; take_antilog         = h.get('take_antilog', True)
//; zero_detect          = h.get('zero_detect', False)
//; a_log_frac_bits      = h.get('a_log_frac_bits', 0)
//; b_log_frac_bits      = h.get('b_log_frac_bits', 0)
//; symmetric_input      = h.get('symmetric_input', False)
//; approx_input_negate  = h.get('approx_input_negate', True)
//; approx_output_negate = h.get('approx_output_negate', False)
//; sign_mag_output      = h.get('sign_mag_output', False)
//; if take_antilog and (a_log_frac_bits or b_log_frac_bits):
//;     a_log_frac_bits = 0
//;     b_log_frac_bits = 0
//;     warning(f"{func_name} take_antilog is set. Setting a_log_frac_bits=b_log_frac_bits=0")
//; # endif
//; a_msb         = a_width - 1
//; b_msb         = b_width - 1
//; a_log_width   = int(math.log(a_width) / math.log(2) + 1) + a_log_frac_bits
//; b_log_width   = int(math.log(b_width) / math.log(2) + 1) + b_log_frac_bits
//; max_log_width = a_log_width if a_log_width > b_log_width else b_log_width
//; log_sum_width = max_log_width + 1
//; product_width = a_width + b_width + (-1 if symmetric_input else 0)
//; a_pad         = f"{log_sum_width - a_log_width}'d0,"
//; b_pad         = f"{log_sum_width - b_log_width}'d0,"
//; out_width     = product_width if take_antilog else log_sum_width + 1
//; antilog_width = (2**log_sum_width) + 1
//; # the antilog of a fractional log is a root, not a shift, so only emit
//; # the helper when the core left the result in the log domain unscaled
//; emit_antilog  = (not take_antilog) and not a_log_frac_bits and not b_log_frac_bits
//; log_shift     = a_log_frac_bits + b_log_frac_bits + 1
//; neg_term      = "" if approx_output_negate else " + 1'b1"
//; a_log_func    = func_name + "_loga"
//; b_log_func    = func_name + "_logb"
//; antilog_func  = func_name + "_antilog"
//; core_func     = func_name + "_core"
//; if not sign_only:
//;     self.include_params = {'func_name': a_log_func, 'input_width': a_width, 'log_frac_bits': a_log_frac_bits, 'symmetric_input': symmetric_input, 'approx_negate': approx_input_negate}
//;     include("ilog2.vpy")
//;     self.include_params = {'func_name': b_log_func, 'input_width': b_width, 'log_frac_bits': b_log_frac_bits, 'symmetric_input': symmetric_input, 'approx_negate': approx_input_negate}
//;     include("ilog2.vpy")
//; else:
//;     out_width = 2
//; # endif
//; _d = getattr(self, func_name, {}); _d['out_width'] = out_width; _d['product_width'] = product_width; setattr(self, func_name, _d)
//; out_type = "      " if sign_mag_output else "signed"
// `func_name`(xA[`a_width`:1], xB[`b_width`:1]), lsb(a:`a_log_frac_bits`,b:`b_log_frac_bits`) antilog:`take_antilog` isym:`symmetric_input` approx(i:`approx_input_negate`,o:`approx_output_negate`) zerodt:`zero_detect`, osm:`sign_mag_output`
//; if sign_only:
function `out_type` [`out_width-1`:0] `func_name`;
input signed [`a_msb`:0] a;
input signed [`b_msb`:0] b;
reg          [`out_width-1`:0] zero;
begin
	zero = { `out_width` { a == `a_msb+1`'d0 || b == `b_msb+1`'d0 } } ;
	case ( { a[`a_width-1`], b[`b_width-1`] } )  // synthesis full_case parallel_case
	2'b00: `func_name` = `out_width`'b01 & ~zero ;
	2'b01: `func_name` = `out_width`'b11 & ~zero ;
	2'b10: `func_name` = `out_width`'b11 & ~zero ;
	2'b11: `func_name` = `out_width`'b01 & ~zero ;
	endcase
end
endfunction
//; else:
//;     if emit_antilog:
// optional antilog of a `func_name`_core result
function signed [`product_width-1`:0] `antilog_func`;
input [`log_sum_width`:0]   l; // `"sm" if sign_mag_output else "signed"`
reg   [`product_width-1`:0] mag;
reg   [`product_width-1`:0] zero;
reg                 l_s;
reg   [`log_sum_width-1`:0] l_m;
begin
	zero = { `product_width` { l == 'd0 } };
//;         if sign_mag_output:
	{ l_s, l_m } = l;
//;         else:
	l_s = l[`log_sum_width`];
	// undo the core's own negate, so the magnitude comes back as it went in
	if (l_s) l_m = ~l[`log_sum_width-1`:0]`neg_term`;
	else     l_m = l[`log_sum_width-1`:0];
//;         # endif
	// one shifter, not up then down: (1 << l_m) >> shift is 2**(l_m - shift)
	mag = `product_width`'d0;
	if (l_m >= `log_sum_width`'d`log_shift`) mag = `product_width`'d1 << (l_m - `log_shift`);
	if (l_s) `antilog_func` = (~mag`neg_term`) & ~zero;
	else     `antilog_func` = mag & ~zero;
end
endfunction
//;     # endif
// core function
function `out_type` [`out_width-1`:0] `core_func`;
input [`a_log_width+1`:0] zslog2a; // { zero_flag, sign, log }
input [`b_log_width+1`:0] zslog2b; // { zero_flag, sign, log }
reg   [`log_sum_width-1`:0] lsum;
reg   [`antilog_width-1`:0] antilog;
reg   [`out_width-1`:0] res, res_sm;
reg   [`out_width-1`:0] zero;
reg   [`a_log_width-1`:0] log2a;
reg   [`b_log_width-1`:0] log2b;
reg   sa, sb, za, zb; // signs and zero detection
begin
	{za, sa, log2a} = zslog2a;
	{zb, sb, log2b} = zslog2b;
//;     if zero_detect:
	zero = { `out_width` { za | zb } } ;
//;     else:
	zero = `out_width`'d0;
//;     # endif
	lsum = {`a_pad` log2a } + {`b_pad` log2b };
//;     if take_antilog:
	antilog = (1<<lsum)>>`a_log_frac_bits+b_log_frac_bits+1`;
	res = antilog[`out_width-1`:0];
//;     else:
	res = {1'b0, lsum[`log_sum_width-1`:0]};
//;     # endif
	res_sm = { sa ^ sb, res[`out_width-2`:0] } & ~zero ;
//;     if sign_mag_output:
	`core_func` = res_sm;
//;     else:
//;         round_term = "" if approx_output_negate else "+1'b1"
	`core_func` = res_sm[`out_width-1`] ? ( ~{ 1'b0, res_sm[`out_width-2`:0]} `round_term` ) : ( {1'b0, res_sm[`out_width-2`:0]} );
//;     # endif
end
endfunction
// main logmult function
function `out_type` [`out_width-1`:0] `func_name`;
input signed [`a_msb`:0] a;
input signed [`b_msb`:0] b;
begin
	`func_name` = `core_func`( { a == 'd0, `a_log_func`(a) }, { b == 'd0, `b_log_func`(b) } );
end
endfunction
//; # endif
