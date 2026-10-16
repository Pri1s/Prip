"""Unit tests for the mutation operators (run with `make mutator-test`)."""

from mutator.operators import Design, enumerate_mutations, localization

SEQ = """module t (
    input  wire       clk,
    input  wire       rst,
    input  wire       en,
    input  wire [3:0] d,
    output reg  [3:0] q,
    output wire       hi
);
    localparam TOP = 4'd9;
    reg [3:0] r;
    integer k;
    assign hi = (q > TOP) ? en : 1'b0;  // comparison
    always @(posedge clk) begin
        if (rst) begin
            q <= 4'd0;
            r <= 4'd0;
        end else if (en) begin
            q <= d + r[2:0];
            r <= {d[1], d[3:1]};
        end else begin
            q <= q;
        end
    end
endmodule
"""

COMB = """module c (
    input  wire [1:0] s,
    input  wire [3:0] a,
    output reg  [3:0] y
);
    integer k;
    always @* begin
        y = 4'h0;
        for (k = 0; k < 2; k = k + 1)
            y = y ^ a;
        case (s)
            2'd0: y = a;
            default: y = ~a;
        endcase
    end
endmodule
"""


def muts(text, op=None):
    ms = enumerate_mutations(Design(text), "test")
    return [m for m in ms if op is None or m.operator == op]


def changed_lines(text, m):
    return [l for l in m.apply(text).splitlines() if l not in text.splitlines()]


def test_every_mutation_is_one_reversible_span():
    for text in (SEQ, COMB):
        for m in muts(text):
            buggy = m.apply(text)
            assert buggy != text
            # Undo: put the original span back where the replacement went.
            undone = buggy[:m.start] + text[m.start:m.end] + buggy[m.start + len(m.replacement):]
            assert undone == text, m


def test_relational_and_arith_swaps():
    notes = {m.note for m in muts(SEQ, "relational_swap")}
    assert notes == {"'>' -> '>='", "'>' -> '<'"}
    assert ["            q <= d - r[2:0];"] == changed_lines(SEQ, muts(SEQ, "arith_swap")[0])


def test_constant_keeps_width_and_base():
    reps = {(m.note, m.replacement) for m in muts(SEQ, "constant_change")}
    assert ("4'd9 -> 10", "10") in reps and ("4'd9 -> 8", "8") in reps
    lines = [changed_lines(COMB, m)[0].strip() for m in muts(COMB, "constant_change")]
    assert "y = 4'h1;" in lines and "2'd1: y = a;" in lines


def test_ports_declarations_and_for_headers_untouched():
    for m in muts(SEQ) + muts(COMB):
        line = changed_lines(SEQ if m in muts(SEQ) else COMB, m)
        assert not any(l.strip().startswith(("input", "output", "for (", "integer")) for l in line), m
    assert not any("k" in (m.replacement, ) for m in muts(COMB, "wrong_signal"))


def test_no_clock_edge_mutations():
    assert not any("negedge" in m.apply(SEQ) for m in muts(SEQ))


def test_statement_delete_removes_whole_line_and_localizes():
    m = next(m for m in muts(SEQ, "stmt_delete") if "r <= {d[1]" in m.note)
    buggy = m.apply(SEQ)
    assert len(buggy.splitlines()) == len(SEQ.splitlines()) - 1
    loc = localization(SEQ, m)
    assert loc["golden_lines"] == [19, 19] and loc["buggy_lines"] == []
    assert loc["missing_at_line"] == 19   # the `end else begin` line moved up into its place
    assert loc["enclosing_lines"][0] == 17


def test_only_block_statements_are_deleted():
    # `q <= q;` is alone in a begin/end, so it can go; case-arm statements without begin/end can't.
    assert any("q <= q;" in m.note for m in muts(SEQ, "stmt_delete"))
    assert not any("y = a;" in m.note for m in muts(COMB, "stmt_delete"))


def test_branch_and_arm_deletes():
    final = muts(SEQ, "branch_delete")
    assert len(final) == 1 and "q <= q;" not in final[0].apply(SEQ)
    arm = muts(SEQ, "elseif_arm_delete")
    assert len(arm) == 1 and "if (en)" not in arm[0].apply(SEQ) and "q <= q;" in arm[0].apply(SEQ)
    items = {m.note for m in muts(COMB, "case_item_delete")}
    assert items == {"delete case item '2'd0'", "delete case item 'default'"}


def test_assignment_kind_swaps():
    nb = muts(SEQ, "nb_to_blocking")
    assert nb and all(m.replacement == "=" for m in nb)
    b2n = muts(COMB, "blocking_to_nb")
    assert b2n and all(m.replacement == "<=" for m in b2n)
    assert not any("for (k <=" in m.apply(COMB) for m in b2n)


def test_bit_vector_operators():
    shifts = {m.note for m in muts(SEQ, "part_select_shift")}
    assert shifts == {"[2:0] -> [3:1]", "[3:1] -> [2:0]"}
    bits = {m.note for m in muts(SEQ, "bit_index_shift")}
    assert bits == {"[1] -> [2]", "[1] -> [0]"}
    assert {m.replacement for m in muts(SEQ, "decl_width_shrink")} == {"2"}   # reg [3:0] r only
    cat = muts(SEQ, "concat_swap")
    assert len(cat) == 1 and "{d[3:1], d[1]}" in cat[0].apply(SEQ)


def test_wrong_signal_same_width_only():
    for m in muts(SEQ, "wrong_signal"):
        old, new = m.note.split(" -> ")
        d = Design(SEQ)
        assert d.width(old) == d.width(new) and old != new


def test_reset_registers():
    assert Design(SEQ).reset_registers("rst") == {"q", "r"}
