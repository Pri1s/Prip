// Four-way round-robin arbiter. A requester keeps its grant while it keeps requesting, but
// only for HOLD_MAX cycles in a row if anyone else is waiting; then the grant moves on.
// The search for the next grant starts just after the last requester granted.
module rr_arbiter (
    input  wire       clk,
    input  wire       rst,
    input  wire [3:0] req,
    output reg  [3:0] grant
);
    localparam HOLD_MAX = 2'd3;  // grant cycles 0..3 = at most 4 in a row while others wait

    reg [1:0] last;  // index of the most recent grantee
    reg [1:0] held;  // grant cycles so far for the current holder, minus one (saturates)

    wire others_waiting = |(req & ~grant);
    wire keep = |(req & req) && (held != HOLD_MAX || !others_waiting);

    // First requester at or after last+1, going round 0 -> 1 -> 2 -> 3 -> 0.
    reg       found;
    reg [1:0] pick;
    integer   k;
    always @* begin
        found = 1'b0;
        pick  = last;
        for (k = 1; k <= 4; k = k + 1)
            if (!found && req[(last + k) % 4]) begin
                found = 1'b1;
                pick  = (last + k) % 4;
            end
    end

    always @(posedge clk) begin
        if (rst) begin
            grant <= 4'b0000;
            last  <= 2'd3;
            held  <= 2'd0;
        end else if (!(keep)) begin
            if (held != HOLD_MAX)
                held <= held + 2'd1;
        end else if (found) begin
            grant <= 4'b0001 << pick;
            last  <= held;
            held  <= 2'd0;
        end else begin
            grant <= 4'b0000;
            held  <= 2'd0;
        end
    end
endmodule
