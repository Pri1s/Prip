"""Grades finished tool-server runs: every <runs-dir>/<run>/ with a submission gets grade.json.

Runs inside the container (the grader needs the answer key and the EDA tools; the tool server
that produced the runs lives on the host). A run without a submission is a failure, not graded.

  python tools/grade_runs.py grade build/tools_check/runs [--check]
      --check compares each run's grade with the check_expect.json the scripted client left
  python tools/grade_runs.py lines bcd_sum_08 token_bucket_07 ...
      prints {bug: a line that counts as exact} (used by the scripted client in tools_check.py)
"""

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from grader.grade import expected_lines, grade_submission, load_bug  # noqa: E402


def grade_one(run_dir: Path) -> dict:
    info = json.loads((run_dir / "run.json").read_text())
    sub = run_dir / "submission" / "submission.json"
    if not sub.exists():
        return {"run": run_dir.name, "bug": info["bug"], "state": info["state"], "repair": "NO_SUBMISSION",
                "exact": False, "block": False}
    s = json.loads(sub.read_text())
    r = grade_submission(load_bug(info["bug"]), run_dir / "submission" / s["file"], s["line"],
                         run_dir / "grade", run_eqy=False)
    return {"run": run_dir.name, "bug": info["bug"], "state": info["state"], "repair": r["repair"]["verdict"],
            "reason": r["repair"]["reason"], "exact": r["localization"]["exact"],
            "block": r["localization"]["block"]}


def grade(runs_dir: Path, check: bool) -> int:
    runs = sorted(d for d in runs_dir.iterdir() if (d / "run.json").exists())
    with ProcessPoolExecutor() as pool:
        results = list(pool.map(grade_one, runs))
    problems = 0
    for d, r in zip(runs, results):
        line = f"{r['run']:<40} {r['repair']:<14} exact={r['exact']!s:<5} block={r['block']!s:<5}"
        if check:
            want = json.loads((d / "check_expect.json").read_text())
            bad = [f"{k} {r[k]} != {v}" for k, v in want.items() if r[k] != v]
            if bad:
                problems += 1
                line += "  MISMATCH: " + "; ".join(bad) + f" ({r.get('reason', '')})"
        print(line)
    (runs_dir / "grades.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"\n{len(runs)} runs graded" + (f", {problems} mismatches" if check else ""))
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("grade")
    g.add_argument("runs_dir", type=Path)
    g.add_argument("--check", action="store_true")
    l = sub.add_parser("lines")
    l.add_argument("bugs", nargs="+")
    a = ap.parse_args()
    if a.cmd == "grade":
        sys.exit(grade(a.runs_dir, a.check))
    out = {}
    for bug_id in a.bugs:
        bug = load_bug(bug_id)
        exact, _ = expected_lines(bug, (ROOT / bug["file"]).read_text())
        out[bug_id] = min(exact)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
