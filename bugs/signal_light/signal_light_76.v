// Traffic-signal controller: cycles red -> green -> yellow -> red with fixed durations.
// A pedestrian request shortens a long remaining green to PED_LEFT more cycles.
module signal_light (
    input  wire       clk,
    input  wire       rst,
    input  wire       ped_req,
    output wire       red,
    output wire       yellow,
    output wire       green,
    output reg  [4:0] remaining
);
    localparam RED_T    = 5'd8;
    localparam GREEN_T  = 5'd24;
    localparam YELLOW_T = 5'd3;
    localparam PED_LEFT = 5'd4;

    localparam S_RED    = 2'd0;
    localparam S_GREEN  = 2'd1;
    localparam S_YELLOW = 2'd2;

    reg [1:0] state;

    assign red    = (state == S_RED);
    assign green  = (state == S_GREEN);
    assign yellow = (state == S_YELLOW);

    // `remaining` counts the cycles left after the current one; at 0 the light changes.
    always @(posedge clk) begin
        if (rst) begin
            state     <= S_RED;
            remaining <= RED_T - 5'd1;
        end else if (remaining == 5'd0) begin
            case (state)
                S_RED:    begin state <= S_GREEN;  remaining <= GREEN_T - 5'd1;  end
                S_GREEN:  begin state <= S_YELLOW; remaining <= YELLOW_T - 5'd1; end
                default:  begin state <= S_RED;    end
            endcase
        end else if (green && ped_req && remaining > PED_LEFT) begin
            remaining <= PED_LEFT;
        end else begin
            remaining <= remaining - 5'd1;
        end
    end
endmodule
