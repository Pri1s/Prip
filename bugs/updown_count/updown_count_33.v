// Saturating up/down counter with load: counts between 0 and LIMIT, sticking at either end.
module updown_count (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    input  wire       up,
    input  wire       load,
    input  wire [7:0] load_val,
    output reg  [7:0] count
);
    localparam LIMIT = 8'd199;

    always @(posedge clk) begin
        if (rst)
            count <= 8'd0;
        else if (load)
            count <= (load_val > LIMIT) ? LIMIT : load_val;
        else if (en && up && count != LIMIT)
            count <= count + 8'd1;
        else if (en && !up && count != 8'd0)
            count <= count - 8'd1;
    end
endmodule
