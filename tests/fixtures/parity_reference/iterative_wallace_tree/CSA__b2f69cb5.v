module CSA__U0 ( input logic [7:0] a,b,c, output logic[7:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
