// signed semi-log multiplier (simplest form) - a*b =~ a << log2(b)
//; import math
//; h       = self.include_params
//; func_name   = h.get('func_name', 'f_slogmult')   # name of the generated Verilog function
//; a_width  = h['a_width']                     # multiplicand (a) bit width
//; b_width  = h['b_width']                     # multiplier (b) bit width
//; symmetric_input    = h.get('symmetric_input', False)            # True: operands never -2^N (forwarded to ilog2)
//; zero_detect  = h.get('zero_detect', True)           # True: force result to 0 when b == 0
//; approx_input_negate = h.get('approx_input_negate', True)          # approximate (ones-complement) input negation in ilog2
//; approx_output_negate = h.get('approx_output_negate', False)         # True: ones-complement output negate (skip +1); False: exact
//; a_msb     = a_width - 1
//; b_msb     = b_width - 1
//; b_log_width    = int(math.log(b_width) / math.log(2) + 1)
//; product_width  = a_width + 2**b_log_width
//; out_width = a_width + b_width - (1 if symmetric_input else 0)
//; b_log_func  = func_name + "_logb"
//; core_func  = func_name + "_core"
//; self.include_params = {'func_name': b_log_func, 'input_width': b_width, 'log_frac_bits': 0, 'symmetric_input': symmetric_input, 'approx_negate': approx_input_negate}
//; include("ilog2.vpy")
//; _d = getattr(self, func_name, {}); _d['out_width'] = out_width; setattr(self, func_name, _d)
// `func_name`(xA[`a_width`:1], xB[`b_width`:1]), isym:`symmetric_input` approx(i:`approx_input_negate`,o:`approx_output_negate`)
function signed [`out_width-1`:0] `func_name`;
input signed [`a_msb`:0] a;
input signed [`b_msb`:0] b;
reg          [`b_log_width`:0] sb_log2b;
begin
	sb_log2b = `b_log_func`(b);
	`func_name`  = `core_func`(a, sb_log2b);
end
endfunction

// core slogmult so that the log function can be made common
function signed [`out_width-1`:0] `core_func`;
input signed [`a_msb`:0] a;
input        [`b_log_width`:0] sb_log2b;
reg          [`out_width-1`:0] zero, res;
reg          [`product_width-1`:0]  mult, asx;
reg          [`b_log_width-1`:0] log2b;
reg          sb;
begin
	{sb, log2b} = sb_log2b;
	asx  = { {`product_width-a_width` { a[`a_msb`] }}, a };
	mult = asx <<< log2b;
//; if approx_output_negate:
	res = sb ? ~mult[`out_width-1`:0] : mult[`out_width-1`:0];
//; else:
	res = sb ? ~mult[`out_width-1`:0] + 1'b1 : mult[`out_width-1`:0];
//; # endif
//; if zero_detect:
	zero    = { `out_width` { log2b == `b_log_width`'d0 } };
	`core_func` = res & ~zero;
//; else:
	`core_func` = res;
//; # endif
	// synthesis translate_off
	if ( log2b > `out_width-a_width` ) $display("Assertion failed in %m log2b > %d", `product_width-out_width`);
	// synthesis translate_on
end
endfunction
