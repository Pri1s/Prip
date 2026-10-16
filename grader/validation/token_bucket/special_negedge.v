// Validation: same logic clocked on the falling edge. The grader must FAIL it (wrong clock
// edge), not crash.
// Token-bucket rate limiter: a request is granted only while a token is available.
// One token is added every REFILL_PERIOD cycles, up to MAX_TOKENS.
module token_bucket (
    input  wire       clk,
    input  wire       rst,
    input  wire       req,
    output wire       grant,
    output reg  [1:0] level
);
    localparam MAX_TOKENS    = 2'd3;
    localparam REFILL_PERIOD = 3'd5;

    reg  [2:0] tick;
    wire       refill = (tick == REFILL_PERIOD - 3'd1);
    wire [1:0] after_use = level - {1'b0, grant};

    assign grant = req && (level != 2'd0);

    always @(negedge clk) begin
        if (rst) begin
            tick  <= 3'd0;
            level <= MAX_TOKENS;
        end else begin
            tick <= refill ? 3'd0 : tick + 3'd1;
            if (refill && after_use < MAX_TOKENS)
                level <= after_use + 2'd1;
            else
                level <= after_use;
        end
    end
endmodule
