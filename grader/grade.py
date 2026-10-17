"""Grades one benchmark submission: did the patch fix the bug, and did the agent name the buggy line?

The two are scored separately: an agent can find the right line and still fail to fix it, or fix
the bug without pinpointing it.

Repair verdict (the patch is graded against the golden design, never against the buggy one):
  PASS          PDR proves the patch equivalent to golden AND the hidden reference test passes
  FAIL          PDR finds a counterexample or rejects the patch, or the reference test fails
                (including a crash or a simulation that never settles), whatever PDR says.
                A fix must work both formally and in simulation: e.g. a `<=` -> `=` change PDR
                proves equivalent can still behave differently in an event-driven simulator.
  INCONCLUSIVE  PDR couldn't decide and the reference test passed; no credit
  ERROR         the grader broke and the reference test passed; rerun, don't score
Both raw results are kept in grade.json. A patch rejected by the source rules (e.g. file-access
system tasks) is never simulated.

Localization: the claimed line is a line number in the ORIGINAL buggy file, as handed to the agent.
  exact  the claimed line is the edited line; for a deletion, the line just before or just after
         the missing code (blank lines and comments skipped)
  block  the claimed line is inside the enclosing block (every exact hit is also a block hit)
A missing or out-of-range claim is false on both.

Usage (inside the container):
  python -m grader.grade --bug token_bucket_07 --patch patch.v --line 24 --work build/grade/x
"""

import argparse
import json
import re
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from grader.equiv import check_equivalence, check_patch_source
from grader.ref_runner import REF_TIMEOUT, run_reference_isolated

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "bugs" / "manifest.jsonl"
COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def load_bug(bug_id: str) -> dict:
    """A bug from the single-bug pool or the Phase 6c multi-bug variants (bugs/multi*/)."""
    for manifest in (MANIFEST, *sorted((ROOT / "bugs").glob("multi*/manifest.jsonl"))):
        if not manifest.exists():
            continue
        for line in manifest.read_text().splitlines():
            if line.strip() and (bug := json.loads(line))["id"] == bug_id:
                return bug
    raise KeyError(f"no bug {bug_id!r} in {MANIFEST} or bugs/multi*/")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def deletion_lines(buggy: str, offset: int) -> set[int]:
    """The lines on either side of the gap a deletion left at `offset` in the buggy file: the
    line of the last code character before it and of the first code character after it."""
    code = COMMENTS.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), buggy)
    lines = set()
    before = next((i for i in range(min(offset, len(code)) - 1, -1, -1) if not code[i].isspace()), None)
    after = next((i for i in range(offset, len(code)) if not code[i].isspace()), None)
    for i in (before, after):
        if i is not None:
            lines.add(_line_of(code, i))
    return lines


def expected_lines(bug: dict, buggy: str) -> tuple[set[int], set[int]]:
    """(lines that count as exact, lines that count as block) in the buggy file. A multi-bug
    variant counts any component's lines."""
    if "components" in bug:
        return ({l for c in bug["components"] for l in c["exact_lines"]},
                {l for c in bug["components"] for l in c["block_lines"]})
    loc = bug["localization"]
    if loc["buggy_lines"]:
        lo, hi = loc["buggy_lines"]
        exact = set(range(lo, hi + 1))
    else:
        # The text before the edit is the same in golden and buggy, so the span start is the gap.
        exact = deletion_lines(buggy, bug["edit"]["golden_span"][0])
    lo, hi = loc["enclosing_lines"]
    return exact, exact | set(range(lo, hi + 1))


def localize(bug: dict, buggy: str, claimed) -> dict:
    exact, block = expected_lines(bug, buggy)
    out = {"claimed_line": claimed, "exact": False, "block": False,
           "exact_lines": sorted(exact), "block_lines": sorted(block)}
    n = len(buggy.splitlines())
    if claimed is None:
        out["reason"] = "no line claimed"
    elif isinstance(claimed, bool) or not isinstance(claimed, int) or not 1 <= claimed <= n:
        out["reason"] = f"claimed line {claimed!r} is not a line of the buggy file (1-{n})"
    else:
        out["exact"], out["block"] = claimed in exact, claimed in block
    return out


def repair_verdict(formal_verdict: str, ref: dict, formal_reason: str = "") -> tuple[str, str]:
    """Combines the PDR verdict and the reference test result into the repair verdict."""
    if formal_verdict == "FAIL":
        return "FAIL", f"formal FAIL: {formal_reason}"
    if ref["status"] != "ok" or ref["failed"]:
        what = {"timeout": "timed out (simulation never settled)", "crash": "crashed"}.get(
            ref["status"], f"failed {ref['failed']}/{ref['tests']}")
        return "FAIL", f"reference test {what} (formal: {formal_verdict})"
    if formal_verdict == "PASS":
        return "PASS", "formal proof and reference test both pass"
    return formal_verdict, f"formal {formal_verdict}; reference test passed"


def grade_submission(bug: dict, patch, claimed_line, work_dir, run_eqy=True,
                     ref_timeout=REF_TIMEOUT) -> dict:
    """Grades a patch for one bug and writes work_dir/grade.json. Returns the same dict."""
    design = ROOT / "designs" / bug["design"]
    meta = json.loads((design / "meta.json").read_text())
    work = Path(work_dir)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    # The patch is copied in under the top module's file name, as the agent would submit it.
    gate = work / f"{meta['top']}.v"
    gate.write_text(Path(patch).read_text(errors="replace"))

    formal = check_equivalence(design / "golden.v", gate, meta, work / "formal", run_eqy=run_eqy)
    if check_patch_source(gate):
        ref = {"status": "skipped", "tests": 0, "failed": 0}   # never simulate a rejected patch
    else:
        ref = run_reference_isolated(design, gate, work / "ref" / "sim", ref_timeout)
    verdict, reason = repair_verdict(formal.verdict, ref, formal.reason)

    result = {
        "bug": bug["id"], "design": bug["design"],
        "repair": {"verdict": verdict, "reason": reason},
        "formal": asdict(formal),
        "reference_test": ref,
        "localization": localize(bug, (ROOT / bug["file"]).read_text(), claimed_line),
    }
    (work / "grade.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bug", required=True, help="bug ID from bugs/manifest.jsonl")
    ap.add_argument("--patch", required=True, help="patched RTL to grade")
    ap.add_argument("--line", type=int, help="claimed buggy line (original buggy file numbering)")
    ap.add_argument("--work", required=True, help="output directory")
    ap.add_argument("--no-eqy", action="store_true", help="skip the EQY diagnostic")
    args = ap.parse_args()
    r = grade_submission(load_bug(args.bug), args.patch, args.line, args.work, not args.no_eqy)
    loc = r["localization"]
    print(f"repair {r['repair']['verdict']}: {r['repair']['reason']}")
    print(f"localization: exact={loc['exact']} block={loc['block']} (claimed {loc['claimed_line']}, "
          f"exact lines {loc['exact_lines']}, block lines {loc['block_lines'][0]}-{loc['block_lines'][-1]})")
    sys.exit(2 if r["repair"]["verdict"] == "ERROR" else 0)


if __name__ == "__main__":
    main()
