"""Unit tests for how the grader reads SBY proof logs (run with `make grader-test`)."""

from grader.equiv import _prove_status

# Trimmed from a real run (mag_compare mutant with an out-of-range bit read): PDR finds the
# counterexample, then the trace replay crashes.
TRACE_CRASH = """\
SBY  5:00:02 [prove] engine_0: Status returned by engine: FAIL
SBY  5:00:02 [prove] engine_0: ValueError: Yosys witness signal mismatch for t__lt[0]: signal not found in design
SBY  5:00:02 [prove] engine_0: finished (returncode=1)
SBY  5:00:02 [prove] ERROR: engine_0: Could not determine aigsmt status.
SBY  5:00:02 [prove] summary: engine_0 (abc pdr) returned FAIL
SBY  5:00:02 [prove] summary: engine_0 did not produce any traces
SBY  5:00:02 [prove] DONE (ERROR, rc=16)
"""

# PDR itself crashes: no proof result, so no verdict.
ENGINE_CRASH = """\
SBY  5:00:02 [prove] engine_0: abc: Segmentation fault
SBY  5:00:02 [prove] ERROR: engine_0: Engine terminated without status.
SBY  5:00:02 [prove] summary: engine_0 (abc pdr) returned ERROR
SBY  5:00:02 [prove] summary: engine_0 did not produce any traces
SBY  5:00:02 [prove] DONE (ERROR, rc=16)
"""

NORMAL_FAIL = """\
SBY  5:00:02 [prove] summary: engine_0 (abc pdr) returned FAIL
SBY  5:00:02 [prove] summary: counterexample trace: prove/engine_0/trace.vcd
SBY  5:00:02 [prove] DONE (FAIL, rc=2)
"""


def test_trace_crash_after_pdr_fail_is_fail():
    assert _prove_status(TRACE_CRASH) == "FAIL_NO_TRACE"


def test_pdr_crash_stays_error():
    assert _prove_status(ENGINE_CRASH) == "ERROR"


def test_pdr_fail_with_another_error_and_a_trace_stays_error():
    # Something else broke after a trace was written: not the case this rule covers.
    log = NORMAL_FAIL.replace("DONE (FAIL, rc=2)", "DONE (ERROR, rc=16)")
    assert _prove_status(log) == "ERROR"


def test_missing_done_line_stays_error():
    assert _prove_status("SBY  5:00:02 [prove] summary: engine_0 (abc pdr) returned FAIL\n") == "ERROR"


def test_ordinary_verdicts_unchanged():
    assert _prove_status(NORMAL_FAIL) == "FAIL"
    assert _prove_status("SBY [prove] DONE (PASS, rc=0)\n") == "PASS"
    assert _prove_status("SBY [prove] DONE (UNKNOWN, rc=4)\n") == "UNKNOWN"
