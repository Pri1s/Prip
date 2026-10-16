// Two-digit BCD adder: adds two packed decimal numbers (00-99) and a carry-in.
// Any input digit above 9 is invalid: the flag goes high and the sum and carry are forced to 0.
module bcd_sum (
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire       cin,
    output wire [7:0] sum,
    output wire       cout,
    output wire       bad
);
    // Low digit: plain binary add, then add 6 if the result passed 9.
    wire [4:0] raw_lo  = a[3:0] + b[3:0] + {3'd0, cin};
    wire       c_lo    = (raw_lo > 5'd9);
    wire [3:0] dig_lo  = c_lo ? raw_lo[3:0] + 4'd6 : raw_lo[3:0];

    // High digit takes the low digit's decimal carry.
    wire [4:0] raw_hi  = a[7:4] + b[7:4] + {3'd0, c_lo};
    wire       c_hi    = (raw_hi > 5'd9);
    wire [3:0] dig_hi  = c_hi ? raw_hi[3:0] + 4'd5 : raw_hi[3:0];

    assign bad  = (a[3:0] > 4'd9) || (a[7:4] > 4'd9) || (b[3:0] > 4'd9) || (b[7:4] > 4'd9);
    assign sum  = bad ? 8'd0 : {dig_hi, dig_lo};
    assign cout = bad ? 1'b0 : c_hi;
endmodule
