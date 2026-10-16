"""Re-verifies the committed eval and dev sets (bugs/eval_set.json, bugs/dev_set.json).

  - the bug pool is unchanged since selection (manifest sha256), and every selected bug exists
    in the manifest with the same stratum, and its buggy file matches the recorded hash
  - the two sets are disjoint
  - each stratum has exactly its quota, no design exceeds its per-stratum cap, and wrong_signal
    is at most a third of each design's picks
  - rerunning the selection with the recorded seed reproduces both files exactly (frozen and
    reproducible), and bugs/SUBSET.md matches them
Pure Python; `make subset-check`.
"""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from mutator.subset import (BUGS, CAPPED_OPERATOR, DESIGN_CAP, DEV_QUOTA, EVAL_QUOTA,  # noqa: E402
                            STRATA, build_sets, load_manifest, report, stratum)


def check_set(s: dict, quota: dict, manifest: dict, manifest_sha: str) -> list[str]:
    name, problems = s["set"], []
    if s["manifest_sha256"] != manifest_sha:
        problems.append(f"{name}: bug pool changed since selection (manifest sha256 differs)")
    if s["size"] != len(s["bugs"]) or len({b["id"] for b in s["bugs"]}) != len(s["bugs"]):
        problems.append(f"{name}: size field or duplicate IDs")
    for e in s["bugs"]:
        m = manifest.get(e["id"])
        if m is None:
            problems.append(f"{name}: {e['id']} not in manifest")
            continue
        if e["stratum"] != stratum(m) or e["buggy_sha256"] != m["buggy_sha256"] or e["file"] != m["file"]:
            problems.append(f"{name}: {e['id']} disagrees with the manifest")
        path = ROOT / e["file"]
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != e["buggy_sha256"]:
            problems.append(f"{name}: {e['file']} missing or changed")
    for st in STRATA:
        c = Counter(e["design"] for e in s["bugs"] if e["stratum"] == st)
        if sum(c.values()) != quota[st]:
            problems.append(f"{name}: stratum {st} has {sum(c.values())} bugs, quota {quota[st]}")
        over = {d: n for d, n in c.items() if n > DESIGN_CAP[st]}
        if over:
            problems.append(f"{name}: stratum {st} over the per-design cap {DESIGN_CAP[st]}: {over}")
    per_design = Counter(e["design"] for e in s["bugs"])
    ws = Counter(e["design"] for e in s["bugs"] if e["operator"] == CAPPED_OPERATOR)
    for d, n in ws.items():
        if n > per_design[d] // 3:
            problems.append(f"{name}: {d} has {n} {CAPPED_OPERATOR} of {per_design[d]} picks (> a third)")
    return problems


def main():
    pool, manifest_sha = load_manifest()
    manifest = {b["id"]: b for b in pool}
    try:
        ev = json.loads((BUGS / "eval_set.json").read_text())
        dev = json.loads((BUGS / "dev_set.json").read_text())
    except FileNotFoundError as e:
        sys.exit(f"FAIL missing {e.filename}; run make subset")

    problems = check_set(ev, EVAL_QUOTA, manifest, manifest_sha) + check_set(dev, DEV_QUOTA, manifest, manifest_sha)
    overlap = {b["id"] for b in ev["bugs"]} & {b["id"] for b in dev["bugs"]}
    if overlap:
        problems.append(f"eval and dev sets overlap: {sorted(overlap)}")
    if not problems:
        ev2, dev2 = build_sets()
        if ev2 != ev or dev2 != dev:
            problems.append("rerunning the selection does not reproduce the committed sets")
        elif (BUGS / "SUBSET.md").read_text() != report(ev, dev, pool):
            problems.append("bugs/SUBSET.md does not match the sets")

    for p in problems:
        print(f"FAIL {p}")
    print(f"\neval {len(ev['bugs'])} + dev {len(dev['bugs'])} bugs | {len(problems)} problems")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
