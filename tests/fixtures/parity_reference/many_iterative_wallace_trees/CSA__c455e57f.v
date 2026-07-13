module CSA__U3 ( input logic [34:0] a,b,c, output logic[34:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
