// Boolean standard-cell library. All state is arbitrary at power-up.
module BUF(input A, output Y); assign Y=A; endmodule
module NOT(input A, output Y); assign Y=~A; endmodule
module AND2(input A,B, output Y); assign Y=A&B; endmodule
module OR2(input A,B, output Y); assign Y=A|B; endmodule
module XOR2(input A,B, output Y); assign Y=A^B; endmodule
module XNOR2(input A,B, output Y); assign Y=~(A^B); endmodule
module NAND2(input A,B, output Y); assign Y=~(A&B); endmodule
module NOR2(input A,B, output Y); assign Y=~(A|B); endmodule
module MUX2(input A,B,S, output Y); assign Y=S?B:A; endmodule
module AOI21(input A,B,C, output Y); assign Y=~((A&B)|C); endmodule
module OAI21(input A,B,C, output Y); assign Y=~((A|B)&C); endmodule
module DFF(input C,D, output reg Q); always @(posedge C) Q<=D; endmodule
module DFFE(input C,D,E, output reg Q); always @(posedge C) if(E) Q<=D; endmodule
module DFFR(input C,D,R, output reg Q); always @(posedge C) if(R) Q<=0; else Q<=D; endmodule
module DFFS(input C,D,S, output reg Q); always @(posedge C) if(S) Q<=1; else Q<=D; endmodule
module DFFRE(input C,D,R,E, output reg Q); always @(posedge C) if(R) Q<=0; else if(E) Q<=D; endmodule
module DFFER(input C,D,R,E, output reg Q); always @(posedge C) if(E) begin if(R) Q<=0; else Q<=D; end endmodule
