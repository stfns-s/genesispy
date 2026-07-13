module CSA__U1 ( input logic [11:0] a,b,c, output logic[11:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
