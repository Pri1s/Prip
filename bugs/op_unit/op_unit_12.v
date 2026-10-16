// 16-bit arithmetic/logic unit with status flags. Purely combinational.
module op_unit (
    input  wire [15:0] x,
    input  wire [15:0] y,
    input  wire [3:0]  sel,
    output reg  [15:0] q,
    output reg         cf,
    output reg         vf,
    output wire        zf,
    output wire        nf
);
    localparam OP_ADD  = 4'd0;
    localparam OP_SUB  = 4'd1;
    localparam OP_AND  = 4'd2;
    localparam OP_OR   = 4'd3;
    localparam OP_XOR  = 4'd4;
    localparam OP_NOR  = 4'd5;
    localparam OP_SLT  = 4'd6;
    localparam OP_SLTU = 4'd7;
    localparam OP_SHL  = 4'd8;
    localparam OP_SHR  = 4'd9;
    localparam OP_SAR  = 4'd10;
    localparam OP_LDH  = 4'd11;

    reg [16:0] wide;

    always @* begin
        q    = 16'h0000;
        cf   = 1'b0;
        vf   = 1'b0;
        wide = 17'h00000;
        case (sel)
            OP_ADD: begin
                wide = {1'b0, x} + {1'b0, y};
                q    = wide[15:0];
                cf   = wide[16];
                vf   = (x[15] == y[15]) && (q[15] != x[15]);
            end
            OP_SUB: begin
                wide = {1'b0, x} - {1'b0, y};
                q    = wide[15:0];
                cf   = wide[16];
                vf   = (x[15] != y[15]) && (q[15] != x[15]);
            end
            OP_AND:  q = x & y;
            OP_OR:   q = x | y;
            OP_XOR:  q = x ^ y;
            OP_NOR:  q = ~(x | y);
            OP_SLT:  q = {15'b0, $signed(y) < $signed(y)};
            OP_SLTU: q = {15'b0, x < y};
            OP_SHL:  q = x << y[3:0];
            OP_SHR:  q = x >> y[3:0];
            OP_SAR:  q = $signed(x) >>> y[3:0];
            OP_LDH:  q = {y[7:0], 8'h00};
            default: q = 16'h0000;
        endcase
    end

    assign zf = (q == 16'h0000);
    assign nf = q[15];
endmodule
