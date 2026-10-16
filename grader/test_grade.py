"""Unit tests for the grading flow's rules (run with `make grader-test`): how the formal verdict
and the reference test combine, how localization is scored, and the patch source rules."""

import pytest

from grader.equiv import check_patch_source
from grader.grade import deletion_lines, load_bug, localize, repair_verdict, ROOT

OK = {"status": "ok", "tests": 1, "failed": 0}
FAILED = {"status": "ok", "tests": 1, "failed": 1}
TIMEOUT = {"status": "timeout", "tests": 1, "failed": 1}
CRASH = {"status": "crash", "tests": 1, "failed": 1}


@pytest.mark.parametrize("formal, ref, want", [
    ("PASS", OK, "PASS"),
    ("PASS", FAILED, "FAIL"),          # proved equivalent, but behaves differently in simulation
    ("PASS", TIMEOUT, "FAIL"),         # simulation never settles
    ("PASS", CRASH, "FAIL"),
    ("FAIL", OK, "FAIL"),              # a proven counterexample wins over a passing test
    ("FAIL", FAILED, "FAIL"),
    ("INCONCLUSIVE", OK, "INCONCLUSIVE"),
    ("INCONCLUSIVE", FAILED, "FAIL"),  # the failing test is evidence enough
    ("ERROR", OK, "ERROR"),
    ("ERROR", TIMEOUT, "FAIL"),
])
def test_repair_verdict(formal, ref, want):
    assert repair_verdict(formal, ref)[0] == want


def test_deletion_of_a_whole_line_skips_blank_lines_and_comments():
    buggy = "a = 1;\n\n// note\n/* block\n comment */\nb = 2;\n"
    gap = buggy.index("\n// note")    # anywhere between a and b
    assert deletion_lines(buggy, gap) == {1, 6}


def test_deletion_inside_a_line_is_that_line():
    buggy = "x;\nbegin s <= 1; end\ny;\n"
    assert deletion_lines(buggy, buggy.index(" end")) == {2}


def test_deletion_at_the_end_of_a_line():
    # The deleted text started with a newline: the gap is between the two lines.
    buggy = "if (a)\n  c <= 1;\nelse\n  c <= 0;\n"
    assert deletion_lines(buggy, buggy.index("\nelse")) == {2, 3}


def test_deletion_at_file_edges():
    assert deletion_lines("a;\n", 0) == {1}
    assert deletion_lines("a;\n", 3) == {1}


@pytest.mark.parametrize("bug_id, exact", [
    ("updown_count_01", [19, 20]),    # removed `else if` branch after line 19
    ("signal_light_78", [35]),        # removed a statement from the middle of line 35
    ("pack_8to16_30", [15, 16]),      # removed the whole line between 15 and 16
    ("bcd_sum_01", [22]),             # an edited line
])
def test_expected_lines_from_the_manifest(bug_id, exact):
    bug = load_bug(bug_id)
    loc = localize(bug, (ROOT / bug["file"]).read_text(), exact[0])
    assert loc["exact_lines"] == exact and loc["exact"] and loc["block"]


def _bug(buggy_lines, enclosing):
    return {"localization": {"buggy_lines": buggy_lines, "enclosing_lines": enclosing},
            "edit": {"golden_span": [0, 0]}}


def test_localize_exact_block_and_miss():
    bug, text = _bug([12, 12], [10, 15]), "x\n" * 20
    assert (localize(bug, text, 12)["exact"], localize(bug, text, 12)["block"]) == (True, True)
    assert (localize(bug, text, 11)["exact"], localize(bug, text, 11)["block"]) == (False, True)
    assert (localize(bug, text, 16)["exact"], localize(bug, text, 16)["block"]) == (False, False)


@pytest.mark.parametrize("claimed", [None, 0, 21, -1, True, "12", 12.0])
def test_localize_missing_or_invalid_claim_scores_nothing(claimed):
    loc = localize(_bug([12, 12], [10, 15]), "x\n" * 20, claimed)
    assert not loc["exact"] and not loc["block"] and loc["reason"]


@pytest.mark.parametrize("src, rejected", [
    ('initial begin f = $fopen("results.xml", "w"); end', True),
    ("initial $readmemh(\"golden.v\", mem);", True),
    ("initial $dumpvars;", True),
    ('initial $display("x // y"); initial $fwrite(f, "x");', True),   # a string can't hide a comment
    ("// initial $fopen(x);", False),
    ('initial $display("$fopen");', False),
    ("assign y = $signed(a) >>> 1; initial $display(\"%d\", y); initial $finish;", False),
])
def test_patch_source_rules(tmp_path, src, rejected):
    rtl = tmp_path / "p.v"
    rtl.write_text(f"module m(input a, output y);\n{src}\nendmodule\n")
    assert bool(check_patch_source(rtl)) == rejected


def _candidate_patch(cid: str) -> tuple[str, str]:
    import json
    c = next(c for c in map(json.loads, (ROOT / "bugs" / "candidates.jsonl").read_text().splitlines())
             if c["cid"] == cid)
    golden = (ROOT / "designs" / c["design"] / "golden.v").read_text()
    s, e = c["edit"]["golden_span"]
    return c["design"], golden[:s] + c["edit"]["replacement"] + golden[e:]


def _processes_mentioning(text: str) -> list[str]:
    from pathlib import Path
    out = []
    for p in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            cmd = p.read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if text in cmd:
            out.append(cmd)
    return out


def test_hung_simulation_times_out_and_is_killed(tmp_path):
    from grader.ref_runner import run_reference_isolated
    design, text = _candidate_patch("op_unit-c0026")   # PDR PASS, `always @*` never settles
    (tmp_path / "op_unit.v").write_text(text)
    r = run_reference_isolated(ROOT / "designs" / design, tmp_path / "op_unit.v", tmp_path / "sim", timeout=5)
    assert r == {"status": "timeout", "tests": 1, "failed": 1}
    assert _processes_mentioning(str(tmp_path)) == []   # the simulator was killed too


def test_patch_cannot_print_a_fake_result(tmp_path):
    from grader.ref_runner import run_reference_isolated
    bug = load_bug("bcd_sum_01")
    text = (ROOT / bug["file"]).read_text().replace(
        "endmodule", 'initial $display("REF_RESULT [1, 0]");\nendmodule')
    (tmp_path / "bcd_sum.v").write_text(text)
    r = run_reference_isolated(ROOT / "designs" / "bcd_sum", tmp_path / "bcd_sum.v", tmp_path / "sim")
    assert r["status"] == "ok" and r["failed"] == 1
