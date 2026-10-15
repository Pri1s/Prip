"""Phase 2 acceptance: every design in designs/ is complete, lints clean, passes its own
reference test, the grader proves it equivalent to itself, and the grader rejects each of its
known-bad controls (designs/<name>/controls/*.v). Runs inside the container
(see `make corpus-check`). Optional arguments limit the check to the named designs.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from grader.equiv import check_equivalence  # noqa: E402
from grader.ref_runner import run_reference  # noqa: E402

DESIGNS = ROOT / "designs"
BUILD = ROOT / "build" / "corpus"
REQUIRED_FILES = ("golden.v", "spec.md", "ref_test.py", "meta.json")
FLOPS = "t:$dff t:$dffe t:$adff t:$adffe t:$sdff t:$sdffe t:$sdffce t:$dffsr t:$dffsre t:$aldff t:$aldffe"


def run(cmd, log):
    """Runs a command, saving its output to log. Returns True on exit code 0."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    log.write_text(proc.stdout + proc.stderr)
    return proc.returncode == 0


def check_design(d: Path) -> list[str]:
    """Returns a list of problems; empty means the design passed."""
    missing = [f for f in REQUIRED_FILES if not (d / f).is_file()]
    if missing:
        return [f"missing {', '.join(missing)}"]

    meta = json.loads((d / "meta.json").read_text())
    top, kind = meta.get("top"), meta.get("kind")
    problems = []
    if meta.get("name") != d.name:
        problems.append(f"meta name {meta.get('name')!r} != directory name")
    if kind not in ("combinational", "sequential"):
        problems.append(f"meta kind {kind!r} is not combinational/sequential")
    if meta.get("origin") not in ("RTLLM", "VerilogEval", "original"):
        problems.append(f"meta origin {meta.get('origin')!r} is not recognised")
    if problems:
        return problems

    out = BUILD / d.name
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    rtl = d / "golden.v"

    # Strict Verilog-2005 compile.
    if not run(["iverilog", "-g2005", "-Wall", "-o", str(out / "lint.vvp"), "-s", top, str(rtl)],
               out / "iverilog.log"):
        problems.append(f"iverilog -g2005 failed (see {out / 'iverilog.log'})")

    # Synthesizable, no latches, and flip-flops present exactly when the design is sequential.
    flop_assert = "select -assert-none" if kind == "combinational" else "select -assert-min 1"
    script = (f"read_verilog {rtl}; hierarchy -check -top {top}; proc; check -assert; "
              f"select -assert-none t:$dlatch t:$adlatch t:$dlatchsr; {flop_assert} {FLOPS}")
    if not run(["yosys", "-q", "-p", script], out / "yosys.log"):
        problems.append(f"yosys lint failed: latch, wrong kind, or synthesis error (see {out / 'yosys.log'})")

    tests, failed = run_reference(d, rtl, out / "sim")
    if tests == 0 or failed:
        problems.append(f"reference test failed on golden ({failed} of {tests} failed)")

    # Control runs: the grader must prove golden equal to itself (it can grade patches to it),
    # and must reject every known-bad control (it can still see bugs in this design).
    r = check_equivalence(rtl, rtl, meta, out / "grade_self")
    if r.verdict != "PASS":
        problems.append(f"grader did not PASS golden vs itself: {r.verdict}: {r.reason}")
    elif r.disagreement:
        print(f"     note: eqy-sby says {r.eqy_sby} for golden vs itself")
    controls = sorted((d / "controls").glob("*.v"))
    if not controls:
        problems.append("no known-bad controls in controls/")
    for c in controls:
        r = check_equivalence(rtl, c, meta, out / f"grade_control_{c.stem}", run_eqy=False)
        if r.verdict != "FAIL":
            problems.append(f"grader did not FAIL control {c.name}: {r.verdict}: {r.reason}")

    return problems


def main():
    names = sys.argv[1:] or sorted(p.name for p in DESIGNS.iterdir() if p.is_dir())
    failures = 0
    for name in names:
        problems = check_design(DESIGNS / name)
        print(f"{'ok  ' if not problems else 'FAIL'} {name}")
        for p in problems:
            print(f"     - {p}")
        failures += bool(problems)
    print(f"\n{len(names) - failures}/{len(names)} designs passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
