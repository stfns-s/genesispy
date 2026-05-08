// Top module for simulation //

// Parameters: default produces a small 2-tree build; XML/JSON can override
// to a richer sweep (see config.json / config.xml -> [2, 5, 16, 32, 64]).
//; widths = parameter('WALLACES_WIDTHS', [4, 8])

module `mname` ();

\`ifdef SIMULATION
   int seed;
\`endif

   //; for N in widths:
   logic [`N-1`:0]     multiplier_`N`;
   logic [`N-1`:0] 	multiplicand_`N`;
   logic [`N-1`:0] 	pp_`N`[`N-1`:0];
   logic [`2*N-1`:0] 	sum_`N`;
   logic [`2*N-1`:0] 	carry_`N`;
   logic [`2*N-1`:0] 	total_`N`;
   logic [`2*N-1`:0] 	expected_`N`;


   assign total_`N` = sum_`N` + carry_`N`;
   assign expected_`N` = multiplier_`N` * multiplicand_`N`;

   // Generate partial products
   //;     for i in range(N):
   assign pp_`N`[`i`] = (multiplicand_`N`[`i`] == 1'b1) ? multiplier_`N` : `N`'b0;
   //;     # endfor

   // Instantiate the wallace tree here
   //;     wallace = unique_inst('wallace', f"wallace_{N}", N=N)
   `wallace.instantiate()`
     (.pp(pp_`N`),
      .sum(sum_`N`),
      .carry(carry_`N`));

   // EXAMPLE: For demonstration of clones
   // ========================================
   //;     wallace_clone = clone_inst(wallace, f"clone_of_wallce_{N}")
   `wallace_clone.instantiate()`
     (.pp(pp_`N`),
      .sum(/* I'll ignore the outputs here*/),
      .carry(/* I'll ignore the outputs here*/));
   // ========================================

\`ifdef SIMULATION
   initial begin
      int i;
      #`N`;
      $display("%t: AGENT `N` IS ALIVE -- NOW RUN TESTS...", $time);
      for (i=0; i<100; i++) begin
	 multiplier_`N` = $random(seed);
	 multiplicand_`N` = $random(seed);
	 #100;
	 assert (expected_`N`== total_`N`)
	   $display("%t: Agent `N`: Calculating 0x%h * 0x%h -- Expected:0x%h -- Found: 0x%h",
		    $time,multiplier_`N`, multiplicand_`N`, expected_`N`, total_`N`);else
	     $fatal(1, "%t: SVA ERROR  Agent `N`: Calculating 0x%h * 0x%h -- Expected:0x%h -- Found: 0x%h",
		    $time,multiplier_`N`, multiplicand_`N`, expected_`N`, total_`N`);
      end // for (i=0; i<10; i++)
      #100;
      $display("%t: AGENT `N` IS DONE", $time);
   end
\`endif
   //; # endfor


\`ifdef SIMULATION
   // general intialization procedure
   initial begin
      int dummy;
      // if this is a "+wave" run, it must record all signals
      if ( $test$plusargs("wave") )
	begin
           $display("%t: Starting Wave Capture",$time);
           //         levels  instance
\`ifdef VCS
           $vcdpluson(0,        top);
	   $vcdplusmemon(0,     top);
\`endif
        end
      // find the seed for this run
      if ( $test$plusargs("seed") )
	begin
\`ifdef VCS
	   $value$plusargs("seed=%d", seed);
\`else
	   void'($value$plusargs("seed=%d", seed));
\`endif
	end else begin
           seed = 12345;
	end
      $display("%t:\tUsing seed %d",$time, seed);
      dummy = $random(seed);
   end
\`endif

endmodule : `mname`
