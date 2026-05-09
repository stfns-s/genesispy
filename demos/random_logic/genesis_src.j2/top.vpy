// Top module for simulation //


module {{ mname }} ();

`ifdef SIMULATION
   int seed;
`endif


   {% for sig_w in (10, 20): %}
   {%     for mux_w in (2, 4, 8): %}
   // Instantiate the OneHot signals here
   logic [{{ sig_w-1 }}:0] mux_{{ sig_w }}_{{ mux_w }}_ins [{{ mux_w-1 }}:0];
   logic [{{ mux_w-1 }}:0] mux_{{ sig_w }}_{{ mux_w }}_sel;
   logic [{{ sig_w-1 }}:0] mux_{{ sig_w }}_{{ mux_w }}_out;

   // Instantiate the OneHot mux here
   {%         onehot = unique_inst('OneHotMux', f"my_onehot_inst_{sig_w}_{mux_w}", SIGWIDTH=sig_w, MUXWIDTH=mux_w) %}
   {{ onehot.instantiate() }}
     (.in(mux_{{ sig_w }}_{{ mux_w }}_ins),
      .sel(mux_{{ sig_w }}_{{ mux_w }}_sel),
      .out(mux_{{ sig_w }}_{{ mux_w }}_out));

`ifdef SIMULATION
   initial begin
      int i;
      mux_{{ sig_w }}_{{ mux_w }}_sel = {{ mux_w }}'b1;
      {%         for idx in range(mux_w + 1): %}
      mux_{{ sig_w }}_{{ mux_w }}_ins[{{ idx }}] = $random(seed);
      {%         endfor %}

      #{{ mux_w+sig_w }};
      $display("%t: AGENT {{ mux_w }}:{{ sig_w }} IS ALIVE -- NOW RUN TESTS...", $time);
      for (i=0; i<{{ mux_w }}; i++) begin
	 mux_{{ sig_w }}_{{ mux_w }}_sel = ({{ mux_w }}'b1 << i);
	 #100;
	 assert (mux_{{ sig_w }}_{{ mux_w }}_out == mux_{{ sig_w }}_{{ mux_w }}_ins[i])
	   $display("%t: Agent {{ mux_w }}:{{ sig_w }}: sell= %b(i=%0b) -- Expected:0x%h -- Found: 0x%h",
		    $time, mux_{{ sig_w }}_{{ mux_w }}_sel, i, mux_{{ sig_w }}_{{ mux_w }}_ins[i], mux_{{ sig_w }}_{{ mux_w }}_out);else
	     $fatal(1, "%t: SVA ERROR  Agent {{ mux_w }}:{{ sig_w }}: sell= %b(i=%0b) -- Expected:0x%h -- Found: 0x%h",
		    $time, mux_{{ sig_w }}_{{ mux_w }}_sel, i, mux_{{ sig_w }}_{{ mux_w }}_ins[i], mux_{{ sig_w }}_{{ mux_w }}_out);

      end // for (i=0; i<{{ mux_w }}; i++)

      #100;
      $display("%t: AGENT {{ mux_w }}:{{ sig_w }} IS DONE", $time);
   end
`endif

{%     endfor %}
{% endfor %}


`ifdef SIMULATION
   // general intialization procedure
   initial begin
      int dummy;
      // if this is a "+wave" run, it must record all signals
      if ( $test$plusargs("wave") )
	begin
           $display("%t: Starting Wave Capture",$time);
           //         levels  instance
`ifdef VCS
           $vcdpluson(0,        top);
	   $vcdplusmemon(0,     top);
`endif
        end
      // find the seed for this run
      if ( $test$plusargs("seed") )
	begin
`ifdef VCS
	   $value$plusargs("seed=%d", seed);
`else
	   void'($value$plusargs("seed=%d", seed));
`endif
	end else begin
           seed = 12345;
	end
      $display("%t:\tUsing seed %d",$time, seed);
      dummy = $random(seed);
   end
`endif


endmodule : {{ mname }}
