// Group accumulator: adds up each group of three valid input samples and presents the total
// for one cycle. `sum` is only meaningful while out_valid is high.
module sample_accum (
    input  wire       clk,
    input  wire       rst,
    input  wire       in_valid,
    input  wire [7:0] in_data,
    output reg        out_valid,
    output reg  [9:0] sum
);
    reg [1:0] taken;  // samples already in the current group (0-2)
    reg [9:0] acc;    // their running total

    wire [9:0] total = acc + {2'b00, in_data};

    always @(posedge clk) begin
        if (rst) begin
            taken     <= 2'd0;
            acc       <= 10'd0;
            out_valid <= 1'b0;
        end else begin
            out_valid <= out_valid && (taken == 2'd2);
            if (in_valid) begin
                if (taken == 2'd2) begin
                    sum   <= total;
                    acc   <= 10'd0;
                    taken <= 2'd0;
                end else begin
                    acc   <= total;
                    taken <= taken + 2'd1;
                end
            end
        end
    end
endmodule
