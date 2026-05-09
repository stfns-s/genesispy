module {{ mname }} (
	{% signal_width = parameter('SIGWIDTH', 4) %}
	{% mux_width = parameter('MUXWIDTH', 4) %}
	input logic [{{ signal_width-1 }}:0] in [{{ mux_width-1 }}:0],
	input logic [{{ mux_width-1 }}:0] sel,
	output logic [{{ signal_width-1 }}:0] out
		);
  always_comb
    begin
       out = in[0]; // default
       unique case (1'b1)
	 {% for idx in range(mux_width): %}
	 sel[{{ idx }}]: out = in [{{ idx }}];
	 {% endfor %}
       endcase

       assert ($onehot(sel))
	 else $error("select is not one hot");
    end // always_comb begin


endmodule
