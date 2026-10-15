// Validation variant: correct: refill timer counts down in a renamed register.
module token_bucket (
    input  wire       clk,
    input  wire       rst,
    input  wire       req,
    output wire       grant,
    output reg  [1:0] level
);
    localparam MAX_TOKENS    = 2'd3;
    localparam REFILL_PERIOD = 3'd5;

    reg  [2:0] countdown;
    wire       refill = (countdown == 3'd0);
    wire [1:0] after_use = level - {1'b0, grant};

    assign grant = req && (level != 2'd0);

    always @(posedge clk) begin
        if (rst) begin
            countdown <= REFILL_PERIOD - 3'd1;
            level     <= MAX_TOKENS;
        end else begin
            countdown <= refill ? REFILL_PERIOD - 3'd1 : countdown - 3'd1;
            if (refill && after_use < MAX_TOKENS)
                level <= after_use + 2'd1;
            else
                level <= after_use;
        end
    end
endmodule
