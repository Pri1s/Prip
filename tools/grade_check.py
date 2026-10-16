"""End-to-end check of the grading flow (grader/grade.py) on every eval and dev bug.

Per bug (bugs/eval_set.json + bugs/dev_set.json):
  - the exact repair (golden.v) claiming the expected line: repair PASS, localization exact
  - the unchanged buggy file, no line claimed: repair FAIL, localization false; the reference
    test result matches the manifest's reference_test_detected
Fair grading: every equivalent mutant in bugs/candidates.jsonl (a correct repair written
differently) must PASS. Must pass both checks: every candidate PDR proved equivalent but simulation
rejected (the token_bucket `<=` -> `=` change, `always @*` blocks that never settle) must FAIL.
Runs inside the container (see `make grade-check`).
"""

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from grader.grade import expected_lines, grade_submission  # noqa: E402

BUGS = ROOT / "bugs"
BUILD = ROOT / "build" / "grade_check"
SIM_REJECTED = {"rejected_formal_pass_sim_fails", "rejected_simsynth_disagree"}


def run(job):
    kind, name, bug, patch_text, line = job
    work = BUILD / kind / name
    work.mkdir(parents=True, exist_ok=True)
    patch = work.parent / f"{name}.v"
    patch.write_text(patch_text)
    return job, grade_submission(bug, patch, line, work, run_eqy=False)


def problems_for(job, r) -> list[str]:
    kind, _, bug, _, line = job
    verdict, loc, ref = r["repair"]["verdict"], r["localization"], r["reference_test"]
    out = []
    want = "PASS" if kind in ("fixed", "rewrite") else "FAIL"
    if verdict != want:
        out.append(f"repair {verdict} (expected {want}): {r['repair']['reason']}")
    if kind == "fixed" and not loc["exact"]:
        out.append(f"claimed line {line} not scored exact (exact lines {loc['exact_lines']})")
    if kind == "unchanged":
        if loc["exact"] or loc["block"]:
            out.append("no claimed line, but localization scored")
        detected = ref["status"] != "ok" or ref["failed"] > 0
        if detected != bug["reference_test_detected"]:
            out.append(f"reference test detected={detected}, manifest says {bug['reference_test_detected']}")
    return out


def main():
    manifest = {b["id"]: b for b in map(json.loads, (BUGS / "manifest.jsonl").read_text().splitlines())}
    ids = [e["id"] for f in ("eval_set.json", "dev_set.json")
           for e in json.loads((BUGS / f).read_text())["bugs"]]
    cands = [json.loads(l) for l in (BUGS / "candidates.jsonl").read_text().splitlines() if l.strip()]
    any_bug = {}   # one bug per design, to grade candidate repairs against (localization unused)
    for b in manifest.values():
        any_bug.setdefault(b["design"], b)

    jobs = []
    for i in ids:
        bug = manifest[i]
        golden = (ROOT / "designs" / bug["design"] / "golden.v").read_text()
        exact, _ = expected_lines(bug, (ROOT / bug["file"]).read_text())
        jobs.append(("fixed", i, bug, golden, min(exact)))
        jobs.append(("unchanged", i, bug, (ROOT / bug["file"]).read_text(), None))
    for c in cands:
        if c["outcome"] == "equivalent":
            kind = "rewrite"
        elif c["outcome"] in SIM_REJECTED and c["grader"]["verdict"] == "PASS":
            kind = "sim_rejected"
        else:
            continue
        golden = (ROOT / "designs" / c["design"] / "golden.v").read_text()
        s, e = c["edit"]["golden_span"]
        jobs.append((kind, c["cid"], any_bug[c["design"]], golden[:s] + c["edit"]["replacement"] + golden[e:], None))

    problems, counts = {}, {}
    with ProcessPoolExecutor(6) as ex:
        for job, r in ex.map(run, jobs):
            kind, name = job[0], job[1]
            counts.setdefault(kind, [0, 0])[0] += 1
            if p := problems_for(job, r):
                problems[f"{kind} {name}"] = p
            else:
                counts[kind][1] += 1
            if kind == "sim_rejected":
                print(f"  {name}: {r['repair']['verdict']} ({r['repair']['reason']})", flush=True)

    for k, v in sorted(problems.items()):
        print(f"FAIL {k}: " + "; ".join(v))
    labels = {"fixed": "golden repair PASS + exact line", "unchanged": "unchanged buggy FAIL",
              "rewrite": "equivalent rewrites PASS", "sim_rejected": "formal-pass/sim-broken FAIL"}
    print("\n" + " | ".join(f"{labels[k]}: {ok}/{n}" for k, (n, ok) in counts.items()))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
