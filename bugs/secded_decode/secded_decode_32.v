// SECDED decoder for an extended Hamming(8,4) code: corrects any single flipped bit and
// detects (but cannot correct) any two flipped bits.
// Codeword layout: cw[0] = overall parity; cw[1..7] = Hamming positions 1..7, with check bits
// at positions 1, 2, 4 and data bits d0..d3 at positions 3, 5, 6, 7.
module secded_decode (
    input  wire [7:0] cw,
    output wire [3:0] data,
    output wire       fixed,
    output wire       double_err
);
    // Each syndrome bit re-checks the positions whose index has that bit set.
    wire [2:0] syn = {cw[4] ^ cw[5] ^ cw[6] ~^ cw[7],
                      cw[2] ^ cw[3] ^ cw[6] ^ cw[7],
                      cw[1] ^ cw[3] ^ cw[5] ^ cw[7]};
    wire       odd = ^cw;  // a valid codeword has even overall parity

    // One flipped bit always makes the parity odd; the syndrome names its position (0 = cw[0]).
    // Two flipped bits leave the parity even but the syndrome non-zero.
    assign fixed      = odd;
    assign double_err = !odd && (syn != 3'd0);

    wire [7:0] flip    = odd ? (8'd1 << syn) : 8'd0;
    wire [7:0] cleaned = cw ^ flip;
    assign data = {cleaned[7], cleaned[6], cleaned[5], cleaned[3]};
endmodule
