"""Runs inside the agent's sandbox container: lints the agent's RTL or runs one of its cocotb tests.

Mounted read-only at /opt/box/box_runner.py; the rest of this repository is never in the sandbox.
The host-side tool server calls it through `docker exec` and reads the last BOX_RESULT line.

The result line is agent-controllable by construction: the agent's own Python test runs as the
same user, so it can print anything, including a fake BOX_RESULT. That's harmless: run_cocotb's
result is feedback to the agent about its own test, never used for scoring (detection is replayed
offline in Phase 6, grading uses the hidden reference test).

Usage (inside the sandbox):
  python /opt/box/box_runner.py lint --rtl /ws/token_bucket.v --top token_bucket --forbid '$assert,...'
  python /opt/box/box_runner.py cocotb --rtl /ws/token_bucket.v --top token_bucket --module test_x \
      --seed 1234 --build /tmp/build_3 [--testcase name]
"""

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TESTS_DIR = "/ws/tests"


def emit(result: dict):
    print("BOX_RESULT " + json.dumps(result), flush=True)


def lint(args):
    out = Path("/tmp/lint")
    out.mkdir(parents=True, exist_ok=True)
    problems, logs = [], []
    p = subprocess.run(["iverilog", "-g2005", "-Wall", "-o", str(out / "lint.vvp"), "-s", args.top, args.rtl],
                       capture_output=True, text=True)
    if text := (p.stdout + p.stderr).strip():
        logs.append("iverilog -g2005 -Wall:\n" + text)
    if p.returncode:
        problems.append("iverilog -g2005 failed")
    # Same front end as the grader (read_verilog -formal), so formal constructs show up as cells.
    forbid = " ".join(f"t:{c}" for c in args.forbid.split(",") if c)
    script = (f"read_verilog -formal {args.rtl}; hierarchy -check -top {args.top}; proc; check; "
              f"select -assert-none {forbid}")
    p = subprocess.run(["yosys", "-q", "-p", script], capture_output=True, text=True)
    if text := (p.stdout + p.stderr).strip():
        logs.append("yosys (elaborate + check):\n" + text)
    if p.returncode:
        problems.append("yosys failed: does not elaborate, or uses formal-only constructs")
    emit({"ok": not problems, "problems": problems, "log": "\n\n".join(logs)})


def _failure_message(el) -> str:
    kind = el.get("error_type") or ""
    msg = (el.get("error_msg") or el.get("message") or el.text or "").strip()
    return f"{kind}: {msg}" if kind else msg


def parse_results(xml_path: Path) -> list[dict]:
    tests = []
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        bad = case.find("failure")
        if bad is None:
            bad = case.find("error")
        tests.append({"name": case.get("name"),
                      "passed": bad is None and case.find("skipped") is None,
                      "skipped": case.find("skipped") is not None,
                      "message": None if bad is None else _failure_message(bad),
                      "sim_time_ns": case.get("sim_time_ns")})
    return tests


def cocotb(args):
    from cocotb_tools.runner import get_runner

    build = Path(args.build)
    runner = get_runner("icarus")
    try:
        runner.build(sources=[args.rtl], hdl_toplevel=args.top, build_dir=build,
                     timescale=("1ns", "1ps"), always=True)
    except (SystemExit, RuntimeError) as e:
        emit({"status": "build_failed", "tests": [], "error": str(e)})
        return
    # The runner hands sys.path to the simulator as PYTHONPATH; that's how it finds the test.
    sys.path.insert(0, TESTS_DIR)
    xml = build / "results.xml"
    try:
        runner.test(hdl_toplevel=args.top, test_module=args.module, build_dir=build, test_dir=build,
                    results_xml=str(xml), seed=args.seed,
                    test_filter=f"^{args.testcase}$" if args.testcase else None)
    except (SystemExit, RuntimeError):
        pass  # a failing test or a simulator crash; results.xml (if any) says which
    if not xml.exists():
        emit({"status": "crash", "tests": []})
        return
    try:
        tests = parse_results(xml)
    except ET.ParseError:
        emit({"status": "crash", "tests": []})
        return
    emit({"status": "finished" if tests else "no_tests", "tests": tests})


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("lint")
    a.add_argument("--rtl", required=True)
    a.add_argument("--top", required=True)
    a.add_argument("--forbid", default="")
    a = sub.add_parser("cocotb")
    a.add_argument("--rtl", required=True)
    a.add_argument("--top", required=True)
    a.add_argument("--module", required=True)
    a.add_argument("--seed", type=int, required=True)
    a.add_argument("--build", required=True)
    a.add_argument("--testcase")
    args = ap.parse_args()
    lint(args) if args.cmd == "lint" else cocotb(args)


if __name__ == "__main__":
    main()
