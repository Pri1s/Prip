// Validation variant: correct: no count register; full/empty from pointers with an extra wrap bit.
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
    reg [WIDTH-1:0] storage [0:(1 << AW)-1];
    reg [AW:0]      head;   // next slot to write, plus wrap bit
    reg [AW:0]      tail;   // next slot to read, plus wrap bit

    assign empty   = (head == tail);
    assign full    = (head[AW] != tail[AW]) && (head[AW-1:0] == tail[AW-1:0]);
    assign rd_data = storage[tail[AW-1:0]];

    always @(posedge clk) begin
        if (rst) begin
            head <= 0;
            tail <= 0;
        end else begin
            if (wr_en && !full) begin
                storage[head[AW-1:0]] <= wr_data;
                head <= head + 1;
            end
            if (rd_en && !empty)
                tail <= tail + 1;
        end
    end
endmodule
