module CSA__U19 ( input logic [130:0] a,b,c, output logic[130:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
