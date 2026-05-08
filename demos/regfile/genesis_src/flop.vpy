/* *****************************************************************************
 * File: flop.vpy
 *
 * Description:
 * My first attempt in using Genesis2 to make a flip-flop generator.
 *
 * Required Genesis2 Controlable Parameters:
 * * FLOP_TYPE		- constant, flop, rflop, eflop, or reflop
 * * FLOP_WIDTH		- integer value specifying register width
 * * FLOP_DEFAULT	- default value for the flop
 *			 (only applies when flop_type=constant|rflop|reflop)
 *
 * ****************************************************************************/


/*******************************************************************************
 * REQUIRED PARAMETERIZATION
 ******************************************************************************/
//; flop_type = parameter('FLOP_TYPE', "REFLOP")
//; flop_default = None
//; if flop_type.lower() in ('constant', 'rflop', 'reflop'):
//;     flop_default = parameter('FLOP_DEFAULT', "0")
//; # endif
//; flop_width = parameter('FLOP_WIDTH', 1)
//;
//; # Check for error assignments
//; _ft = flop_type.lower()
//; if _ft not in ('constant', 'flop', 'rflop', 'eflop', 'reflop'):
//;     raise ValueError(f"Flop_type parameter = -->{flop_type}<-- is not allowed! Allowed values: constant, flop, rflop, eflop, or reflop.")
//; # endif

module `mname`(
    //inputs
  //; if 'constant' not in flop_type.lower():
    input logic                 Clk,
    input logic [`flop_width-1`:0] data_in,
  //; # endif
  //; if 'rflop' in flop_type.lower() or 'reflop' in flop_type.lower():
    input logic 		Reset,
  //; # endif
  //; if 'eflop' in flop_type.lower() or 'reflop' in flop_type.lower():
    input logic 		Enable,
  //; # endif

    //outputs
    output logic [`flop_width-1`:0] data_out
             );

    //; if flop_type.lower() == 'constant':
      assign data_out = `flop_width`'d`flop_default`;
    //; else:
      always @ (posedge Clk) begin
      //;     if 'rflop' in flop_type.lower() or 'reflop' in flop_type.lower():
      if (Reset) begin
	 data_out <= `flop_width`'d`flop_default`;
      end
      else begin
      //;     # endif
      //;     if 'eflop' in flop_type.lower() or 'reflop' in flop_type.lower():
	 if (Enable)
      //;     # endif
	    data_out <= data_in;
      //;     if 'rflop' in flop_type.lower() or 'reflop' in flop_type.lower():
      end // else: !if(Reset)
      //;     # endif
   end // always @ (posedge Clk)
   //; # endif

endmodule // `mname`
