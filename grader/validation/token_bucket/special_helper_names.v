// Validation variant: correct: helper modules named gold and miter_top must not collide with the grader.
module gold (input wire [1:0] level, output wire empty);
    assign empty = (level == 2'd0);
endmodule

module miter_top (input wire [1:0] a, input wire [1:0] b, output wire [1:0] y);
    assign y = a - b;
endmodule

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
    wire [1:0] after_use;
    wire       no_tokens;
    gold u_empty (.level(level), .empty(no_tokens));
    miter_top u_sub (.a(level), .b({1'b0, grant}), .y(after_use));

    assign grant = req && !no_tokens;

    always @(posedge clk) begin
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
