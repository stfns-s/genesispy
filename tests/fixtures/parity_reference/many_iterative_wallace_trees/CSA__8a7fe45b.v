module CSA__U20 ( input logic [132:0] a,b,c, output logic[132:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
