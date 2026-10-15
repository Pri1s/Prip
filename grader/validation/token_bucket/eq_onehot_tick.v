// Validation variant: correct: one-hot refill phase ring, case-based level update.
module token_bucket (
    input  wire       clk,
    input  wire       rst,
    input  wire       req,
    output wire       grant,
    output reg  [1:0] level
);
    reg  [4:0] phase;              // one-hot: bit i set = i cycles since the last refill
    wire       refill = phase[4];
    wire [1:0] after_use = grant ? level - 2'd1 : level;

    assign grant = req & |level;

    always @(posedge clk) begin
        if (rst) begin
            phase <= 5'b00001;
            level <= 2'd3;
        end else begin
            phase <= {phase[3:0], phase[4]};
            case ({refill, after_use == 2'd3})
                2'b10:   level <= after_use + 2'd1;
                default: level <= after_use;
            endcase
        end
    end
endmodule
