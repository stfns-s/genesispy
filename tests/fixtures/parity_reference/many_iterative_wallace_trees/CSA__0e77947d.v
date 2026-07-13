module CSA__U10 ( input logic [31:0] a,b,c, output logic[31:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
