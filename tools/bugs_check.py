"""Re-verifies the committed bug pool (bugs/manifest.jsonl) against the current golden designs.

Per bug:
  - the buggy file and the golden design match the hashes recorded at generation time
    (a changed golden makes its bugs stale: rerun `make bugs`)
  - undoing the recorded edit turns the buggy file back into golden.v byte for byte, and the
    localization lines exist in the buggy file (the answer key is exact)
  - the ID is opaque (design name + number: nothing about the operator or line)
  - the grader still FAILs it against golden
Per design (fair grading): the grader PASSes golden against itself (the exact repair), and
PASSes up to REWRITES_PER_DESIGN equivalent mutants from bugs/candidates.jsonl (correct repairs
written differently, cross-checked by the reference test and random simulation when generated).
Runs inside the container (see `make bugs-check`). Optional arguments limit it to some designs.
"""

import hashlib
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from grader.equiv import check_equivalence  # noqa: E402

BUGS = ROOT / "bugs"
BUILD = ROOT / "build" / "bugs_check"
REWRITES_PER_DESIGN = 3


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def static_problems(bug: dict) -> list[str]:
    design = ROOT / "designs" / bug["design"]
    golden = (design / "golden.v").read_text()
    path = ROOT / bug["file"]
    if not path.exists():
        return [f"missing {bug['file']}"]
    buggy = path.read_text()
    problems = []
    if sha(golden) != bug["golden_sha256"]:
        problems.append("golden.v changed since generation (stale bug; rerun make bugs)")
    if sha(buggy) != bug["buggy_sha256"]:
        problems.append("buggy file changed since generation")
    s, e = bug["edit"]["golden_span"]
    rep, orig = bug["edit"]["replacement"], bug["edit"]["original"]
    if golden[s:e] != orig or golden[:s] + rep + golden[e:] != buggy:
        problems.append("recorded edit does not turn golden into the buggy file")
    elif buggy[:s] + orig + buggy[s + len(rep):] != golden:
        problems.append("undoing the edit does not reproduce golden")
    n = len(buggy.splitlines())
    loc = bug["localization"]
    lines = loc["buggy_lines"] + loc["enclosing_lines"] + ([loc["missing_at_line"]] if "missing_at_line" in loc else [])
    if any(not 1 <= x <= n + 1 for x in lines):
        problems.append(f"localization lines {lines} outside the buggy file ({n} lines)")
    if not re.fullmatch(rf"{re.escape(bug['design'])}_\d+", bug["id"]) or Path(bug["file"]).stem != bug["id"]:
        problems.append(f"ID {bug['id']!r} is not opaque")
    return problems


def grade(job):
    kind, name, design, gate_text = job
    d = ROOT / "designs" / design
    meta = json.loads((d / "meta.json").read_text())
    work = BUILD / design / name
    work.mkdir(parents=True, exist_ok=True)
    gate = work / f"{meta['top']}.v"
    gate.write_text(gate_text)
    r = check_equivalence(d / "golden.v", gate, meta, work / "grade", run_eqy=False)
    return kind, name, design, r.verdict, r.reason


def main():
    only = set(sys.argv[1:])
    bugs = [json.loads(l) for l in (BUGS / "manifest.jsonl").read_text().splitlines() if l.strip()]
    bugs = [b for b in bugs if not only or b["design"] in only]
    cands = [json.loads(l) for l in (BUGS / "candidates.jsonl").read_text().splitlines() if l.strip()]
    designs = sorted({b["design"] for b in bugs} | ({c["design"] for c in cands if not only or c["design"] in only}))

    problems = {b["id"]: static_problems(b) for b in bugs}
    jobs = [("bug", b["id"], b["design"], (ROOT / b["file"]).read_text()) for b in bugs if (ROOT / b["file"]).exists()]
    for d in designs:
        golden = (ROOT / "designs" / d / "golden.v").read_text()
        jobs.append(("golden", "golden", d, golden))
        eq = [c for c in cands if c["design"] == d and c["outcome"] == "equivalent"][:REWRITES_PER_DESIGN]
        for c in eq:
            s, e = c["edit"]["golden_span"]
            jobs.append(("rewrite", c["cid"], d, golden[:s] + c["edit"]["replacement"] + golden[e:]))

    design_problems = []
    with ProcessPoolExecutor(6) as ex:
        for kind, name, design, verdict, reason in ex.map(grade, jobs):
            want = "FAIL" if kind == "bug" else "PASS"
            if verdict != want:
                msg = f"grader says {verdict} (expected {want}): {reason}"
                (problems.setdefault(name, []) if kind == "bug" else design_problems).append(
                    msg if kind == "bug" else f"{design} {kind} {name}: {msg}")
    rewrites = sum(j[0] == "rewrite" for j in jobs)

    bad = {k: v for k, v in problems.items() if v}
    for k, v in sorted(bad.items()):
        print(f"FAIL {k}: " + "; ".join(v))
    for p in design_problems:
        print(f"FAIL {p}")
    print(f"\n{len(bugs) - len(bad)}/{len(bugs)} bugs OK | golden PASS on {len(designs)} designs, "
          f"{rewrites} equivalent rewrites checked | {len(design_problems)} design problems")
    sys.exit(1 if bad or design_problems else 0)


if __name__ == "__main__":
    main()
