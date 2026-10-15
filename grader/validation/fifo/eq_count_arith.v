// Validation variant: correct: count updated arithmetically instead of by case
// Synchronous FIFO, 4 entries x 8 bits. Writes when full and reads when empty are ignored.
module fifo #(
    parameter WIDTH = 8,
    parameter AW    = 2
) (
    input              clk,
    input              rst,
    input              wr_en,
    input  [WIDTH-1:0] wr_data,
    input              rd_en,
    output [WIDTH-1:0] rd_data,
    output             full,
    output             empty
);
    localparam DEPTH = 1 << AW;

    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [AW-1:0]    wr_ptr;
    reg [AW-1:0]    rd_ptr;
    reg [AW:0]      count;

    wire do_wr = wr_en && !full;
    wire do_rd = rd_en && !empty;

    assign full    = (count == DEPTH);
    assign empty   = (count == 0);
    assign rd_data = mem[rd_ptr];

    always @(posedge clk) begin
        if (rst) begin
            wr_ptr <= 0;
            rd_ptr <= 0;
            count  <= 0;
        end else begin
            if (do_wr) begin
                mem[wr_ptr] <= wr_data;
                wr_ptr      <= wr_ptr + 1;
            end
            if (do_rd)
                rd_ptr <= rd_ptr + 1;
            count <= count + {{AW{1'b0}}, do_wr} - {{AW{1'b0}}, do_rd};
        end
    end
endmodule
