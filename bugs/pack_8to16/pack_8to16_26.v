// Byte-to-word packer: joins each pair of valid input bytes into one 16-bit word,
// first byte in the low half. out_valid pulses for one cycle per finished word.
module pack_8to16 (
    input  wire        clk,
    input  wire        rst,
    input  wire        in_valid,
    input  wire [7:0]  in_byte,
    output reg         out_valid,
    output reg  [15:0] out_word,
    output reg         waiting
);
    reg [7:0] low_byte;

    always @(posedge clk) begin
        if (rst) begin
            waiting   <= 1'b0;
            out_valid <= 1'b0;
            out_word  <= 16'd0;
            low_byte  <= 8'd0;
        end
    end
endmodule
