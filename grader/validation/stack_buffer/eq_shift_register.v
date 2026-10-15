// Validation variant: correct: entries kept in a shift register with the top always in slot 0,
// and the fill level kept as a thermometer code instead of a count.
module stack_buffer (
    input  wire       clk,
    input  wire       rst,
    input  wire       push,
    input  wire       pop,
    input  wire [3:0] din,
    output reg  [3:0] dout,
    output wire [3:0] top,
    output wire       empty,
    output wire       full
);
    reg [3:0] s0, s1, s2, s3, s4, s5;
    reg [5:0] fill;  // fill[i] high when slot i holds an entry

    assign empty = !fill[0];
    assign full  = fill[5];
    assign top   = s0;

    always @(posedge clk) begin
        if (rst) begin
            fill <= 6'd0;
            dout <= 4'd0;
        end else if (pop && !empty) begin
            dout <= s0;
            {s0, s1, s2, s3, s4} <= {s1, s2, s3, s4, s5};
            fill <= {1'b0, fill[5:1]};
        end else if (push && !full) begin
            {s1, s2, s3, s4, s5} <= {s0, s1, s2, s3, s4};
            s0   <= din;
            fill <= {fill[4:0], 1'b1};
        end
    end
endmodule
