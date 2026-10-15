// Known-bad control (grader-only): the difference loses its borrow bit, so lt reads bit 5 of a 6-bit subtraction. The grader must reject this.
// 6-bit magnitude comparator: compares a with b as unsigned or as signed two's-complement numbers.
module mag_compare (
    input  wire [5:0] a,
    input  wire [5:0] b,
    input  wire       is_signed,
    output wire       gt,
    output wire       eq,
    output wire       lt
);
    // Flipping the sign bit maps signed order onto unsigned order (-32 -> 0, ..., 31 -> 63).
    wire [5:0] ua = {a[5] ^ is_signed, a[4:0]};
    wire [5:0] ub = {b[5] ^ is_signed, b[4:0]};

    // a - b with one extra bit: the top bit is the borrow, set exactly when ua < ub.
    wire [6:0] diff = {1'b0, ua} - {1'b0, ub};

    assign lt = diff[5];
    assign eq = (diff[5:0] == 6'd0);
    assign gt = !lt && !eq;
endmodule
