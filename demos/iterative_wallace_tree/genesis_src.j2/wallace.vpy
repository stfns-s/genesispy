{% # Import Libs %}
{% from math import floor %}

// PARAMETERS
{% N = parameter('N', 4) %}

// Wallace tree for N={{ N }} partioal products of width N={{ N }} //
module {{ mname }}
  ( input logic [{{ N-1 }}:0] pp[{{ N-1 }}:0],
    output logic [{{ 2*N-1 }}:0] sum,carry
   );

   {% height = N %}
   {% width = 2*N %}
   {% step = 0 %}
   // make pps rectangular (insert 0s!)
   logic [{{ 2*N-1 }}:0] 	      pp0_step{{ step }};
   assign pp0_step{{ step }} = \{{({{ N }}){1'b0}}, pp[0]};
   {% for i in range(1, N): %}
   logic [{{ 2*N-1 }}:0] 	      pp{{ i }}_step{{ step }};
   assign pp{{ i }}_step{{ step }} = \{{({{ N-i }}){1'b0}}, pp[{{ i }}], {{ "{" }}{{ i }}{1'b0}}};
   {% endfor %}


   {% while height > 2: %}
   {%     step += 1 %}
   {%     width += 1 %}
   // STARTING TREE REDUCTION STEP {{ step }}
   {%     for i in range(floor(height/3)): %}
   logic [{{ width-1 }}:0]       pp{{ 2*i }}_step{{ step }};
   logic [{{ width-1 }}:0]       pp{{ 2*i+1 }}_step{{ step }};
   {%         csa_obj = unique_inst('CSA', f"csa_step{step}_{i}", Width=width-1) %}
   {{ csa_obj.instantiate() }} (.a(pp{{ 3*i }}_step{{ step-1 }}),
      		      .b(pp{{ 3*i+1 }}_step{{ step-1 }}),
      		      .c(pp{{ 3*i+2 }}_step{{ step-1 }}),
      		      .s(pp{{ 2*i }}_step{{ step }}[{{ width-2 }}:0]),
      		      .co(pp{{ 2*i+1 }}_step{{ step }}[{{ width-1 }}:1]));

   assign pp{{ 2*i }}_step{{ step }}[{{ width-1 }}] = 1'b0;
   assign pp{{ 2*i+1 }}_step{{ step }}[0] = 1'b0;
   {%     endfor %}

   // Left overs:
   {%     for i in range(height % 3): %}
   {%         old_idx = i + 3*floor(height/3) %}
   {%         new_idx = i + 2 * floor(height/3) %}
   logic [{{ width-1 }}:0] pp{{ new_idx }}_step{{ step }};
   assign pp{{ new_idx }}_step{{ step }} = {1'b0, pp{{ old_idx }}_step{{ step-1 }}};
   {%     endfor %}
   {%     height = 2 * floor(height/3) + height%3 %}
   {% endwhile %}

   // Ignore all the top bits and assign final PPs to output
   assign sum = pp0_step{{ step }}[{{ 2*N-1 }}:0];
   assign carry = pp1_step{{ step }}[{{ 2*N-1 }}:0];
endmodule : {{ mname }}
