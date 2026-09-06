    // unsigned modulo - a % b, and 0 when b is 0
//; from vexpr import lit
//; h         = self.include_params
//; func_name = h.get('func_name', 'f_umod')
//; iwidth    = h.get('iwidth', 8)
//; lifetime  = h.get('lifetime', 'static')
    function `lifetime` unsigned [`iwidth-1`:0] `func_name`;
        input unsigned [`iwidth-1`:0] a;
        input unsigned [`iwidth-1`:0] b;
        reg [`iwidth`:0] r;
        int i;
        begin
            r = {`iwidth+1` {1'b0}};
            if (b == `lit(0, iwidth, signed=False)`)
                `func_name` = `lit(0, iwidth, signed=False)`;   // 0 on divide by zero
            else begin
                for (i = `iwidth-1`; i >= 0; i--) begin
                    r = {r[`iwidth-1`:0], a[i]};
                    if (r >= {1'b0, b}) r = r - {1'b0, b};
                end
                `func_name` = r[`iwidth-1`:0];
            end
        end
    endfunction
