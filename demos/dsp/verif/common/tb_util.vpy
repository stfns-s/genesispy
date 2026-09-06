    // shared testbench helpers: 64-bit reference arithmetic, checking, data output, reporting
    integer tb_n      = 0;
    integer tb_skipped = 0;
    integer tb_fails  = 0;
    integer tb_fd     = 0;
    longint signed tb_maxdiff = 0;

    // floor division: SystemVerilog / truncates toward zero, hardware shifts floor
    function longint signed fdiv(input longint signed n, d);
        begin
            fdiv = n / d;
            if (n % d != 0 && ((n < 0) != (d < 0))) fdiv = fdiv - 1;
        end
    endfunction

    // sign-extend the low w bits of v, so a truncated result compares as the hardware's does
    function longint signed tb_sext(input longint signed v, input integer w);
        longint signed mask;
        begin
            mask   = (64'd1 << w) - 64'd1;
            tb_sext = (((v >> (w - 1)) & 64'd1) != 0) ? (v | ~mask) : (v & mask);
        end
    endfunction

    function longint signed clamp(input longint signed v, lo, hi);
        clamp = (v < lo) ? lo : (v > hi) ? hi : v;
    endfunction

    // got is 4-state so an X out of the function fails rather than converting to 0
    task tb_check(input logic signed [63:0] got, input longint signed exp, input string ctx);
        begin
            tb_n = tb_n + 1;
            if (got !== exp) begin
                tb_fails = tb_fails + 1;
                if (tb_fails <= 10)
                    $display("  mismatch %s got=%0d exp=%0d", ctx, got, exp);
            end
        end
    endtask

    task tb_skip;
        tb_skipped = tb_skipped + 1;
    endtask

    task tb_data_open(input string cfg, input string cols);
        string path;
        begin
            if ($value$plusargs("data=%s", path)) begin
                tb_fd = $fopen(path, "w");
                if (tb_fd == 0) $fatal(1, "cannot open data file %s", path);
                $fwrite(tb_fd, "# %s\n", cfg);
                $fwrite(tb_fd, "%s\n", cols);
            end
        end
    endtask

    task tb_data_row(input string row);
        if (tb_fd != 0) $fwrite(tb_fd, "%s\n", row);
    endtask

    // largest |got - exp| over the mismatches, for a testbench that reports how far off
    // its worst case was. tb_check already counts them, so nothing here counts again.
    task tb_diff(input logic signed [63:0] got, input longint signed exp);
        longint signed d;
        begin
            if (got !== exp) begin
                d = exp - 64'(got);
                if (d < 0)           d          = -d;
                if (d > tb_maxdiff)  tb_maxdiff = d;
            end
        end
    endtask

    task tb_stats(input string cfg);
        $display("  stats %s -- %0d mismatches, max |y-exp| = %0d", cfg, tb_fails, tb_maxdiff);
    endtask

    task tb_report(input string cfg);
        begin
            if (tb_fd != 0) $fclose(tb_fd);
            if (tb_fails == 0)
                $display("PASS %s -- %0d cases, %0d skipped", cfg, tb_n, tb_skipped);
            else begin
                $display("FAIL %s -- %0d cases, %0d skipped, %0d mismatches",
                         cfg, tb_n, tb_skipped, tb_fails);
                $fatal(1, "mismatches in %s", cfg);
            end
        end
    endtask

    // A waveform for an interactive run. The checked path never defines DUMP: it reads the
    // PASS or FAIL line and has no use for a trace.
\`ifdef DUMP
    initial begin
        $dumpfile("dump.vcd");
        $dumpvars(0, `mname`);
    end
\`endif
