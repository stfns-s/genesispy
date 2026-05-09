module {{ mname }};
   /******************************************************************
    * Calls to the unique_inst method / generate function invoke the
    * generation of the relevant modules based on the template.
    * Verilog instantiation is (intentionally) separated and must
    * appear after the object was created.
    * ***************************************************************/


   {% const_flop_obj = unique_inst('flop', 'const_flop_eg', FLOP_TYPE='constant', FLOP_DEFAULT=0xFF, FLOP_WIDTH=32) %}
   {{ const_flop_obj.instantiate() }} (...);

   {% simple_flop_obj = unique_inst('flop', 'simple_flop_eg', FLOP_TYPE='flop', FLOP_DEFAULT=0b10101, FLOP_WIDTH=32) %}
   {{ simple_flop_obj.instantiate() }} (...);

   {% rflop_flop_obj = unique_inst('flop', 'rflop_flop_eg', FLOP_TYPE='rflop', FLOP_DEFAULT=7, FLOP_WIDTH=32) %}
   {{ rflop_flop_obj.instantiate() }} (...);

   {% eflop_flop_obj = unique_inst('flop', 'eflop_flop_eg', FLOP_TYPE='eflop', FLOP_DEFAULT=17, FLOP_WIDTH=32) %}
   {{ eflop_flop_obj.instantiate() }} (...);

   {% # Register with no default value binding so that we can bind it later %}
   {% # through the XML input. %}
   {% reflop_flop_obj = unique_inst('flop', 'reflop_flop_eg', FLOP_TYPE='reflop', FLOP_WIDTH=32) %}
   {{ reflop_flop_obj.instantiate() }} (...);
endmodule : {{ mname }}
