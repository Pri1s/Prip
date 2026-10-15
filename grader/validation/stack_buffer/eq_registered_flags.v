// Validation variant: correct: empty and full are registers updated alongside the count.
module stack_buffer (
    input  wire       clk,
    input  wire       rst,
    input  wire       push,
    input  wire       pop,
    input  wire [3:0] din,
    output reg  [3:0] dout,
    output wire [3:0] top,
    output reg        empty,
    output reg        full
);
    reg [3:0] mem [0:5];
    reg [2:0] used;

    assign top = mem[used - 3'd1];

    always @(posedge clk) begin
        if (rst) begin
            used  <= 3'd0;
            dout  <= 4'd0;
            empty <= 1'b1;
            full  <= 1'b0;
        end else if (pop && !empty) begin
            dout  <= mem[used - 3'd1];
            used  <= used - 3'd1;
            empty <= (used == 3'd1);
            full  <= 1'b0;
        end else if (push && !full) begin
            mem[used] <= din;
            used  <= used + 3'd1;
            empty <= 1'b0;
            full  <= (used == 3'd5);
        end
    end
endmodule
