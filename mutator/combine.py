"""Phase 6c probe: three-bug variants, built from bugs already in the single-bug pool.

Each variant applies three accepted single bugs of one design at once (separate golden lines,
non-overlapping edits), then goes through the same gates as every single bug (mutator/generate.py:
lint, PDR FAIL with a counterexample from reset, depth, simulation checks, reference test). It is
kept only if, in addition, every pair of its edits still FAILs on its own, so no two edits cancel
and a repair must undo all three.

A repair is graded as before (whole-design equivalence to golden + hidden reference test), so a
patch passes only when all three bugs are fixed. A claimed line counts as exact if it is any
component's exact line (block likewise); the manifest stores both per component, in the variant's
own line numbering.

Two sets, each in its own directory with its own manifest (answer key):
  probe (default)  bugs/multi/       2 per design, seed 20261017, probe_set.json  (`make bugs-multi`)
  eval             bugs/multi_eval/  12 per design, a new seed, eval_set.json     (`make bugs-multi-eval`)
The eval set is fresh: its components exclude every single bug used in the probe or in the dev
set (both were already run by a model), and a single bug appears in at most 2 eval variants.
Runs inside the container.
"""

import argparse
import hashlib
import itertools
import json
import random
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from grader.equiv import check_equivalence  # noqa: E402
from grader.grade import deletion_lines  # noqa: E402
from mutator.generate import _gates, depth_bin, provenance  # noqa: E402
from mutator.operators import line_of  # noqa: E402

BUGS = ROOT / "bugs"
BUILD = ROOT / "build" / "bugs_multi"
K = 3
SETS = {  # name: (directory, id letter, seed, variants per design, max uses of one single bug)
    "probe": ("multi", "m", 20261017, 2, None),
    "eval": ("multi_eval", "e", 20261018, 12, 2),
}


def apply_edits(golden: str, comps: list[dict]) -> str:
    text = golden
    for c in sorted(comps, key=lambda c: c["edit"]["golden_span"][0], reverse=True):
        s, e = c["edit"]["golden_span"]
        text = text[:s] + c["edit"]["replacement"] + text[e:]
    return text


def compatible(comps: list[dict]) -> bool:
    """Edits don't overlap and sit on different golden lines."""
    spans = sorted((tuple(c["edit"]["golden_span"]), tuple(c["localization"]["golden_lines"])) for c in comps)
    return all(a[0][1] <= b[0][0] and a[1][1] < b[1][0] for a, b in zip(spans, spans[1:]))


def _shift(c) -> int:
    s, e = c["edit"]["golden_span"]
    return len(c["edit"]["replacement"]) - (e - s)


def _nl_shift(c) -> int:
    return c["edit"]["replacement"].count("\n") - c["edit"]["original"].count("\n")


def localization(golden: str, combined: str, comps: list[dict]) -> list[dict]:
    """Exact and block lines of each component, in the combined file's numbering."""
    out = []
    for c in comps:
        s, _ = c["edit"]["golden_span"]
        before = [o for o in comps if o["edit"]["golden_span"][1] <= s]
        off = s + sum(_shift(o) for o in before)
        rep = c["edit"]["replacement"]
        if rep:
            exact = set(range(line_of(combined, off), line_of(combined, off + len(rep) - 1) + 1))
        else:
            exact = deletion_lines(combined, off)

        def to_combined(single_buggy_line: int) -> int:
            # single-bug file line -> golden line -> combined file line
            b_start = line_of(apply_edits(golden, [c]), s)
            g = single_buggy_line if single_buggy_line <= b_start else single_buggy_line - _nl_shift(c)
            return g + sum(_nl_shift(o) for o in comps if line_of(golden, o["edit"]["golden_span"][1]) < g)

        lo, hi = c["localization"]["enclosing_lines"]
        block = exact | set(range(to_combined(lo), to_combined(hi) + 1))
        out.append({"bug": c["id"], "operator": c["operator"], "family": c["family"],
                    "exact_lines": sorted(exact), "block_lines": sorted(block)})
    return out


def try_design(task) -> dict:
    """Draws triples for one design until PER_DESIGN are accepted (or MAX_TRIES run out)."""
    design, comps_pool, name, seed, per_design, max_uses = task
    design_dir = ROOT / "designs" / design
    meta = json.loads((design_dir / "meta.json").read_text())
    golden_rtl = design_dir / "golden.v"
    golden = golden_rtl.read_text()
    rng = random.Random(f"{seed}:{design}")
    accepted, tried, seen, uses = [], [], set(), {}
    for n in range(max(12, per_design * 3)):
        if len(accepted) == per_design:
            break
        avail = comps_pool if max_uses is None else [c for c in comps_pool if uses.get(c["id"], 0) < max_uses]
        if len(avail) < K:
            break
        for _ in range(200):
            comps = sorted(rng.sample(avail, K), key=lambda c: c["id"])
            key = tuple(c["id"] for c in comps)
            if key not in seen and compatible(comps):
                break
        else:
            break
        seen.add(key)
        work = BUILD / name / design / f"try{n:02d}"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        mutant = work / f"{meta['top']}.v"
        combined = apply_edits(golden, comps)
        mutant.write_text(combined)
        rec = {"design": design, "components": list(key), "try": n}
        t0 = time.monotonic()
        try:
            _gates(rec, design_dir, meta, golden_rtl, mutant, work)
            if rec["outcome"] == "accepted":
                for i, pair in enumerate(itertools.combinations(comps, 2)):
                    p = work / f"pair{i}" / f"{meta['top']}.v"
                    p.parent.mkdir()
                    p.write_text(apply_edits(golden, list(pair)))
                    r = check_equivalence(golden_rtl, p, meta, p.parent / "grade", run_eqy=False)
                    if r.verdict != "FAIL":
                        rec["outcome"] = "rejected_pair_not_fail"
                        rec["reason"] = f"edits {pair[0]['id']} + {pair[1]['id']} together: {r.verdict}"
                        break
        except Exception as e:
            rec["outcome"], rec["reason"] = "error", f"{type(e).__name__}: {e}"
        rec["seconds"] = round(time.monotonic() - t0, 1)
        tried.append(rec)
        if rec["outcome"] == "accepted":
            rec["localization"] = localization(golden, combined, comps)
            rec["buggy"] = combined
            accepted.append(rec)
            for c in key:
                uses[c] = uses.get(c, 0) + 1
        shutil.rmtree(work, ignore_errors=True)
    return {"design": design, "meta": meta, "golden": golden, "accepted": accepted, "tried": tried}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("designs", nargs="*")
    ap.add_argument("--set", choices=sorted(SETS), default="probe")
    a = ap.parse_args()
    dirname, letter, seed, per_design, max_uses = SETS[a.set]
    out_dir = BUGS / dirname
    pool = [json.loads(l) for l in (BUGS / "manifest.jsonl").read_text().splitlines() if l.strip()]
    excluded = set()
    if a.set == "eval":   # fresh: no single bug a model has already seen
        excluded |= {b["id"] for b in json.loads((BUGS / "dev_set.json").read_text())["bugs"]}
        excluded |= {c["bug"] for l in (BUGS / "multi" / "manifest.jsonl").read_text().splitlines()
                     for c in json.loads(l)["components"]}
    by_design = {}
    for b in pool:
        if b["id"] not in excluded:
            by_design.setdefault(b["design"], []).append(b)
    names = a.designs or sorted(by_design)
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    prov = provenance()
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(try_design, [(d, by_design[d], a.set, seed, per_design, max_uses) for d in names]))

    manifest, report = [], []
    for res in results:
        d, meta, golden = res["design"], res["meta"], res["golden"]
        for i, rec in enumerate(res["accepted"], 1):
            bid = f"{d}_{letter}{i:02d}"
            path = out_dir / d / f"{bid}.v"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rec["buggy"])
            manifest.append({
                "id": bid, "design": d, "kind": meta["kind"], "top": meta["top"],
                "file": str(path.relative_to(ROOT)), "components": rec["localization"],
                "formal": {"pdr_cex_step": rec["grader"]["pdr_cex_step"], **rec["depth"], "depth_bin": depth_bin(rec),
                           "failing_outputs": rec["grader"]["failing_outputs"]},
                "reference_test_detected": rec["reference_test_detected"],
                "golden_sha256": hashlib.sha256(golden.encode()).hexdigest(),
                "buggy_sha256": hashlib.sha256(rec["buggy"].encode()).hexdigest(),
                "provenance": {**prov, "seed": seed, "k": K, "set": a.set},
            })
        outcomes = {}
        for t in res["tried"]:
            outcomes[t["outcome"]] = outcomes.get(t["outcome"], 0) + 1
        report.append(f"{d:<16} accepted {len(res['accepted'])}/{per_design}  tries {len(res['tried'])}  {outcomes}")
        for t in res["tried"]:
            if t["outcome"] not in ("accepted",) and t.get("reason"):
                report.append(f"    try{t['try']:02d} {t['components']}: {t['outcome']}: {t['reason'][:160]}")

    text = "".join(json.dumps(x) + "\n" for x in sorted(manifest, key=lambda x: x["id"]))
    (out_dir / "manifest.jsonl").write_text(text)
    (out_dir / f"{a.set}_set.json").write_text(json.dumps({
        "seed": seed, "k": K, "set": f"{a.set}-multi", "size": len(manifest),
        "manifest_sha256": hashlib.sha256(text.encode()).hexdigest(), "excluded_single_bugs": len(excluded),
        "bugs": [{"id": x["id"]} for x in sorted(manifest, key=lambda x: x["id"])]}, indent=1) + "\n")
    (out_dir / "REPORT.txt").write_text("\n".join(report) + "\n")
    print("\n".join(report))
    print(f"\n{len(manifest)} three-bug variants -> {out_dir.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
