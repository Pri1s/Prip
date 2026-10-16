// Serial pattern watcher: flags each occurrence of the bit pattern 1101 (overlaps allowed).
module pattern_watch (
    input  wire clk,
    input  wire rst,
    input  wire din,
    output wire seen
);
    // State = longest tail of the input so far that is also a head of 1101.
    localparam ST_NONE  = 3'd0;  // no useful tail
    localparam ST_1     = 3'd1;  // tail "1"
    localparam ST_11    = 3'd2;  // tail "11"
    localparam ST_110   = 3'd3;  // tail "110"
    localparam ST_FOUND = 3'd4;  // tail "1101"

    reg [2:0] state;
    reg [2:0] state_next;

    always @* begin
        case (state)
            ST_NONE:  state_next = din ? ST_1     : ST_NONE;
            ST_1:     state_next = din ? ST_11    : ST_NONE;
            ST_11:    state_next = din ? ST_11    : ST_110;
            ST_110:   state_next = din ? ST_FOUND : ST_NONE;
            ST_FOUND: state_next = din ? ST_110    : ST_NONE;
            default:  state_next = ST_NONE;
        endcase
    end

    always @(posedge clk) begin
        if (rst)
            state <= ST_NONE;
        else
            state <= state_next;
    end

    assign seen = (state == ST_FOUND);
endmodule
