module CSA__U14 ( input logic [68:0] a,b,c, output logic[68:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
