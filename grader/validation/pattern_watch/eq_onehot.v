// Validation variant: correct: one-hot state in a renamed register.
module pattern_watch (
    input  wire clk,
    input  wire rst,
    input  wire din,
    output wire seen
);
    // tail[0]=none, tail[1]="1", tail[2]="11", tail[3]="110", tail[4]="1101"
    reg [4:0] tail;
    wire [4:0] tail_next;

    assign tail_next[0] = !din && (tail[0] || tail[1] || tail[4]) || !din && tail[3];
    assign tail_next[1] = din && tail[0];
    assign tail_next[2] = din && (tail[1] || tail[2] || tail[4]);
    assign tail_next[3] = !din && tail[2];
    assign tail_next[4] = din && tail[3];

    always @(posedge clk) begin
        if (rst)
            tail <= 5'b00001;
        else
            tail <= tail_next;
    end

    assign seen = tail[4];
endmodule
