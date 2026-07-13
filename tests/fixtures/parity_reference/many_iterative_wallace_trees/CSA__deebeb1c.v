module CSA__U22 ( input logic [134:0] a,b,c, output logic[134:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
