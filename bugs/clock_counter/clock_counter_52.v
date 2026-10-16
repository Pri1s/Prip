// Scaled-down clock: three cascaded counters (sec 0-9, min 0-5, hr 0-11) that advance once
// per enabled cycle. The full cycle is 10 * 6 * 12 = 720 enabled cycles.
module clock_counter (
    input  wire       clk,
    input  wire       rst,
    input  wire       run,
    output reg  [3:0] sec,
    output reg  [2:0] min,
    output reg  [3:0] hr
);
    localparam SEC_LAST = 4'd9;
    localparam MIN_LAST = 3'd5;
    localparam HR_LAST  = 4'd11;

    wire sec_wrap = run && (sec == SEC_LAST);
    wire min_wrap = sec_wrap && (min == MIN_LAST);
    wire hr_wrap  = min_wrap && (hr == HR_LAST);

    always @(posedge clk) begin
        if (rst) begin
            sec <= 4'd0;
            min <= 3'd0;
            hr  <= 4'd0;
        end else if (run) begin
            sec <= sec_wrap ? 4'd0 : sec + 4'd1;
            if (!(sec_wrap))
                min <= min_wrap ? 3'd0 : min + 3'd1;
            if (min_wrap)
                hr <= hr_wrap ? 4'd0 : hr + 4'd1;
        end
    end
endmodule
