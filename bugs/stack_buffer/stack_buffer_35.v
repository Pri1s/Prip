// Six-entry, 4-bit-wide stack (last in, first out) with a registered pop output and a
// combinational view of the top entry. Storage is not cleared by reset.
module stack_buffer (
    input  wire       clk,
    input  wire       rst,
    input  wire       push,
    input  wire       pop,
    input  wire [3:0] din,
    output reg  [3:0] dout,
    output wire [3:0] top,
    output wire       empty,
    output wire       full
);
    localparam DEPTH = 3'd6;

    reg [3:0] mem [0:5];
    reg [2:0] used;  // number of entries held; mem[used-1] is the top

    assign empty = (used == 3'd0);
    assign full  = (used == DEPTH);
    assign top   = mem[used - 3'd1];  // meaningless while empty

    always @(posedge clk) begin
        if (rst) begin
            used <= 3'd0;
            dout <= 4'd0;
        end else if (pop && !empty) begin
            dout <= mem[used - 3'd1];
            used <= used - 3'd1;
        end else if (push && !full) begin
            mem[used] <= din;
            used <= used + 3'd2;
        end
    end
endmodule
