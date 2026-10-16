"""Runs a design's hidden reference test (designs/<name>/ref_test.py) against any RTL file.

Used by the corpus check on golden RTL, the bug generator on mutants, and the grader on
submitted patches. Untrusted RTL goes through run_reference_isolated, which runs the test in its
own process group so a simulation that never settles (e.g. an `always @*` block that keeps
retriggering itself) can be stopped.
"""

import json
import os
import re
import secrets
import signal
import subprocess
import sys
from pathlib import Path

from cocotb_tools.runner import get_results, get_runner

ROOT = Path(__file__).resolve().parent.parent
# Seconds before a simulation counts as hung. The slowest golden reference test (seq_divider)
# takes about 5 s, so this leaves room for a loaded machine.
REF_TIMEOUT = 60


def run_reference(design_dir: Path, rtl: Path, build_dir: Path) -> tuple[int, int]:
    """Returns (tests run, tests failed). A simulator crash counts as all tests failing."""
    design_dir, rtl, build_dir = Path(design_dir).resolve(), Path(rtl).resolve(), Path(build_dir).resolve()
    top = json.loads((design_dir / "meta.json").read_text())["top"]
    runner = get_runner("icarus")
    runner.build(
        sources=[rtl],
        hdl_toplevel=top,
        build_dir=build_dir,
        timescale=("1ns", "1ps"),
        always=True,
    )
    # The runner hands sys.path to the simulator as PYTHONPATH, so this is how it finds
    # ref_test.py. Every design's test has the same module name, so remove it afterwards.
    sys.path.insert(0, str(design_dir))
    try:
        results = runner.test(
            hdl_toplevel=top,
            test_module="ref_test",
            build_dir=build_dir,
            test_dir=build_dir,
            results_xml=str(build_dir / "results.xml"),
        )
        return get_results(results)
    except (SystemExit, RuntimeError):
        return (1, 1)
    finally:
        sys.path.remove(str(design_dir))


def run_reference_isolated(design_dir: Path, rtl: Path, build_dir: Path,
                           timeout: int = REF_TIMEOUT) -> dict:
    """Runs the reference test in a subprocess, with a timeout. Returns {"status", "tests",
    "failed"}: status "ok", "timeout" or "crash" (no result reported); a timeout or crash counts
    as all tests failing. The output is saved next to build_dir as ref.log."""
    build_dir = Path(build_dir).resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    # The simulation shares stdout with the result line, so the line carries a per-run token: a
    # patch can't $display a fake result it can't predict.
    token = secrets.token_hex(16)
    cmd = [sys.executable, "-m", "grader.ref_runner", str(Path(design_dir).resolve()),
           str(Path(rtl).resolve()), str(build_dir), token]
    # A new session puts the simulator (a grandchild) in our process group, so a timeout kills
    # it too instead of leaving it spinning.
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
        status = None
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        out += f"\nTIMEOUT after {timeout}s"
        status = "timeout"
    (build_dir.parent / "ref.log").write_text(out)
    m = re.findall(rf"^REF_RESULT {token} \[(\d+), (\d+)\]$", out, re.M)
    if status is None and m:
        return {"status": "ok", "tests": int(m[-1][0]), "failed": int(m[-1][1])}
    return {"status": status or "crash", "tests": 1, "failed": 1}


if __name__ == "__main__":
    tests, failed = run_reference(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    print(f"REF_RESULT {sys.argv[4]} [{tests}, {failed}]", flush=True)
