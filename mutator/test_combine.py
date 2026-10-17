"""Tests for mutator/combine.py (three-bug variants) and multi-bug localization in grader/grade.py.
Run in the container: `make mutator-test`."""

import json

import pytest

from grader.grade import ROOT, expected_lines, localize
from mutator.combine import apply_edits, compatible, localization

GOLDEN = """module m(input a, input b, output reg y, output z);
  wire t;
  assign t = a & b;
  always @* begin
    y = t;
    if (a)
      y = 1'b0;
  end
  assign z = a | b;
endmodule
"""


def comp(cid, golden, original, replacement, enclosing, nth=0, operator="op"):
    start = -1
    for _ in range(nth + 1):
        start = golden.index(original, start + 1)
    end = start + len(original)
    gl = [golden.count("\n", 0, start) + 1, golden.count("\n", 0, max(start, end - 1)) + 1]
    # enclosing lines are in the single-bug file's numbering
    return {"id": cid, "operator": operator, "family": "f",
            "edit": {"golden_span": [start, end], "original": original, "replacement": replacement},
            "localization": {"golden_lines": gl, "enclosing_lines": enclosing}}


def test_apply_and_localize_with_a_line_deletion():
    a = comp("a", GOLDEN, "a & b", "a | b", [3, 3])
    # deletes the whole two-line if statement (lines 6-7), so later lines move up by 2
    d = comp("d", GOLDEN, "    if (a)\n      y = 1'b0;\n", "", [4, 6])
    z = comp("z", GOLDEN, "a | b", "a ^ b", [9, 9])
    comps = [a, d, z]
    assert compatible(comps)
    combined = apply_edits(GOLDEN, comps)
    assert "assign t = a | b;" in combined and "if (a)" not in combined and "assign z = a ^ b;" in combined
    loc = {c["bug"]: c for c in localization(GOLDEN, combined, comps)}
    lines = combined.splitlines()
    assert loc["a"]["exact_lines"] == [3]
    assert loc["z"]["exact_lines"] == [7] and "a ^ b" in lines[6]
    assert loc["d"]["exact_lines"] == [5, 6]      # the lines around the gap: "y = t;" and "end"
    assert set(loc["d"]["block_lines"]) >= {4, 5, 6}
    assert loc["z"]["block_lines"] == [7]


def test_incompatible_edits():
    a = comp("a", GOLDEN, "a & b", "a | b", [3, 3])
    a2 = comp("a2", GOLDEN, "b;", "a;", [3, 3])            # same golden line
    over = comp("o", GOLDEN, "t = a", "t = b", [3, 3])      # overlapping span
    assert not compatible([a, a2])
    assert not compatible([a, over])


def test_grader_counts_any_components_line():
    bug = {"id": "x", "file": "unused", "components": [
        {"exact_lines": [3], "block_lines": [3]}, {"exact_lines": [5, 6], "block_lines": [4, 5, 6]},
        {"exact_lines": [7], "block_lines": [7]}]}
    exact, block = expected_lines(bug, "")
    assert exact == {3, 5, 6, 7} and block == {3, 4, 5, 6, 7}
    text = "\n".join(["x"] * 9)
    assert localize(bug, text, 6)["exact"] and localize(bug, text, 4) == {**localize(bug, text, 4), "exact": False, "block": True}
    assert not localize(bug, text, 9)["block"]


MULTI = ROOT / "bugs" / "multi" / "manifest.jsonl"


@pytest.mark.skipif(not MULTI.exists(), reason="no bugs/multi yet (make bugs-multi)")
def test_generated_variants_point_at_their_edits():
    pool = {b["id"]: b for b in map(json.loads, (ROOT / "bugs" / "manifest.jsonl").read_text().splitlines())}
    for v in map(json.loads, MULTI.read_text().splitlines()):
        text = (ROOT / v["file"]).read_text()
        lines = text.splitlines()
        golden = (ROOT / "designs" / v["design"] / "golden.v").read_text()
        comps = [pool[c["bug"]] for c in v["components"]]
        assert apply_edits(golden, comps) == text, v["id"]
        assert len(v["components"]) == 3 and len({c["bug"] for c in v["components"]}) == 3
        for c, b in zip(v["components"], comps):
            rep = b["edit"]["replacement"]
            if rep and "\n" not in rep:
                assert any(rep in lines[l - 1] for l in c["exact_lines"]), (v["id"], c)
            assert set(c["exact_lines"]) <= set(c["block_lines"])
