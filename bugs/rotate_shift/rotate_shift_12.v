// 8-bit barrel shifter: moves d left or right by 0-7 places, either filling with zeros
// or rotating the bits that fall off one end back in at the other.
module rotate_shift (
    input  wire [7:0] d,
    input  wire [2:0] amt,
    input  wire       left,
    input  wire       rot,
    output wire [7:0] q
);
    // Three stages shift by 1, 2 and 4 places. A left shift is done as a right shift of the
    // bit-reversed value, so every stage only needs the right-shift form.
    function [7:0] reverse;
        input [7:0] v;
        integer i;
        begin
            for (i = 0; i < 8; i = i + 1)
                reverse[i] = v[7 - i];
        end
    endfunction

    wire [7:0] s0 = left ? reverse(d) : d;
    wire [7:0] s1 = amt[0] ? {rot ? s0[0]   : 1'b0,  s0[7:1]} : s0;
    wire [7:0] s2 = amt[1] ? {rot ? s1[1:0] : 2'b00, s1[7:2]} : s1;
    wire [7:0] s3 = amt[2] ? {rot ? s2[3:0] : 4'h0,  s2[7:4]} : s2;

    assign q = !(left) ? reverse(s3) : s3;
endmodule
