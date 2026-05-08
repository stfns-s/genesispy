module CSA__U ( input logic [129:0] a,b,c, output logic[129:0] s, co); assign s = a ^ b ^c; assign co = a&b | b&c | a&c; endmodule
