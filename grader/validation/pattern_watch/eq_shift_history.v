// Validation variant: correct: compares the last four input bits instead of tracking a state machine.
module pattern_watch (
    input  wire clk,
    input  wire rst,
    input  wire din,
    output wire seen
);
    reg [3:0] history;   // oldest bit in [3]; zeros after reset can't fake a leading 1

    always @(posedge clk) begin
        if (rst)
            history <= 4'b0000;
        else
            history <= {history[2:0], din};
    end

    assign seen = (history == 4'b1101);
endmodule
