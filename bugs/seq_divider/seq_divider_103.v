// Multi-cycle 6-bit divider (restoring, one quotient bit per cycle), unsigned or signed.
// Handshake: an operation is accepted when start is high while ready; the result is held with
// done high until ack. quotient/remainder are only meaningful while done is high.
module seq_divider (
    input  wire       clk,
    input  wire       rst,
    input  wire       start,
    input  wire       is_signed,
    input  wire [5:0] dividend,
    input  wire [5:0] divisor,
    input  wire       ack,
    output wire       ready,
    output reg        done,
    output wire [5:0] quotient,
    output wire [5:0] remainder
);
    reg       busy;
    reg [2:0] step;
    reg [5:0] rem, quo, mag_dvs, saved_dvd;
    reg       neg_q, neg_r, by_zero;

    // Divide magnitudes; fix the signs at the end.
    wire [5:0] mag_dvd_in = (is_signed && dividend[5]) ? -dividend : dividend;
    wire [5:0] mag_dvs_in = (is_signed && divisor[5])  ? -divisor  : divisor;

    // One restoring step: bring down the next dividend bit, subtract the divisor if it fits.
    wire [6:0] shifted = {rem, quo[5]};
    wire       fits    = (shifted >= {1'b0, mag_dvs});
    wire [6:0] reduced = shifted - {1'b0, quotient};

    assign ready = !busy && !done;

    always @(posedge clk) begin
        if (rst) begin
            busy <= 1'b0;
            done <= 1'b0;
            step <= 3'd0;
        end else if (ready && start) begin
            busy      <= 1'b1;
            step      <= 3'd0;
            rem       <= 6'd0;
            quo       <= mag_dvd_in;
            mag_dvs   <= mag_dvs_in;
            saved_dvd <= dividend;
            neg_q     <= is_signed && (dividend[5] ^ divisor[5]);
            neg_r     <= is_signed && dividend[5];
            by_zero   <= (divisor == 6'd0);
        end else if (busy) begin
            rem  <= fits ? reduced[5:0] : shifted[5:0];
            quo  <= {quo[4:0], fits};
            step <= step + 3'd1;
            if (step == 3'd5) begin
                busy <= 1'b0;
                done <= 1'b1;
            end
        end else if (done && ack) begin
            done <= 1'b0;
        end
    end

    assign quotient  = by_zero ? 6'h3F     : (neg_q ? -quo : quo);
    assign remainder = by_zero ? saved_dvd : (neg_r ? -rem : rem);
endmodule
