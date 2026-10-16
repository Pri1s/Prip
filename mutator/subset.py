"""Phase 3b: select the frozen evaluation set and a disjoint dev set from the bug pool.

Strata (the axis the research question is about is depth):
  comb-0      combinational bugs (depth is always 0)
  seq-1-2     sequential bugs, minimum counterexample depth 1-2
  seq-3-5                                               3-5
  seq-6+                                                6 or more
The eval set takes EVAL_QUOTA per stratum (54 comb + 3 x 42 seq = 180, 70% sequential); the dev
set takes DEV_QUOTA per stratum from what is left (30). The dev set is for building and tuning
the agent; the eval set is only for reported results.

Within a stratum the quota is spread over designs as evenly as their bug counts allow (water
filling), never above DESIGN_CAP, so no single design (seq_divider holds 126 of the 274 deep
bugs) decides a stratum. Inside each (stratum, design) cell bugs are drawn at random, with
wrong_signal (34% of the pool) limited so it stays at most a third of each design's picks.
Families are reported, not given quotas.

Selection is deterministic from SEED and the manifest. The sets are frozen: once
bugs/eval_set.json exists this refuses to overwrite it unless --force is given, because
changing the eval set after seeing results biases the benchmark.

Writes bugs/eval_set.json, bugs/dev_set.json, bugs/SUBSET.md. Pure Python; `make subset`.
"""

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUGS = ROOT / "bugs"

SEED = 20261016
STRATA = ["comb-0", "seq-1-2", "seq-3-5", "seq-6+"]
EVAL_QUOTA = {"comb-0": 54, "seq-1-2": 42, "seq-3-5": 42, "seq-6+": 42}
DEV_QUOTA = {"comb-0": 9, "seq-1-2": 7, "seq-3-5": 7, "seq-6+": 7}
DESIGN_CAP = {"comb-0": 11, "seq-1-2": 6, "seq-3-5": 8, "seq-6+": 8}  # eval set; checked
CAPPED_OPERATOR = "wrong_signal"  # at most a third of each design's picks


def stratum(bug: dict) -> str:
    if bug["kind"] == "combinational":
        return "comb-0"
    return "seq-" + bug["formal"]["depth_bin"]


def load_manifest() -> tuple[list[dict], str]:
    text = (BUGS / "manifest.jsonl").read_text()
    bugs = [json.loads(l) for l in text.splitlines() if l.strip()]
    return bugs, hashlib.sha256(text.encode()).hexdigest()


def water_fill(avail: dict[str, int], quota: int, rng: random.Random) -> dict[str, int]:
    """Most even split of quota over designs given how many bugs each has. Designs left at the
    top level after the even part are chosen at random for the remainder."""
    if sum(avail.values()) < quota:
        raise SystemExit(f"stratum has {sum(avail.values())} bugs, quota {quota}")
    level = 0
    while sum(min(a, level + 1) for a in avail.values()) <= quota:
        level += 1
    alloc = {d: min(a, level) for d, a in avail.items()}
    extra = quota - sum(alloc.values())
    room = sorted(d for d, a in avail.items() if a > level)
    for d in rng.sample(room, extra):
        alloc[d] += 1
    return alloc


def draw(cell: list[dict], n: int, ws_left: int, rng: random.Random) -> list[dict]:
    """n random bugs from one (stratum, design) cell, taking at most ws_left wrong_signal bugs
    unless the cell has too few other bugs."""
    pool = sorted(cell, key=lambda b: b["id"])
    rng.shuffle(pool)
    picked, skipped = [], []
    for b in pool:
        if len(picked) == n:
            break
        if b["operator"] == CAPPED_OPERATOR:
            if ws_left <= 0:
                skipped.append(b)
                continue
            ws_left -= 1
        picked.append(b)
    picked += skipped[:n - len(picked)]
    return sorted(picked, key=lambda b: b["id"])


def rebalance(alloc: dict, by_cell: dict, rng: random.Random) -> None:
    """A design whose cells are mostly wrong_signal can be forced over its third by the even
    split (pattern_watch: depth 1-2 and 6+ are mostly wrong_signal). Move one pick at a time from
    such a cell to another design in the same stratum that has room, until every design fits."""
    nonws = {k: sum(b["operator"] != CAPPED_OPERATOR for b in v) for k, v in by_cell.items()}

    def forced(d):
        return sum(max(0, n - nonws[k]) for k, n in alloc.items() if k[1] == d)

    def total(d):
        return sum(n for k, n in alloc.items() if k[1] == d)

    while True:
        over = sorted(d for d in {k[1] for k in alloc} if forced(d) > total(d) // 3)
        if not over:
            return
        d = over[0]
        s = max((k for k in alloc if k[1] == d and alloc[k] > nonws[k]), key=lambda k: (alloc[k] - nonws[k], k))[0]
        room = [e for (st, e), n in alloc.items() if st == s and e != d
                and n < min(len(by_cell[(s, e)]), DESIGN_CAP[s]) and n < nonws[(s, e)]]
        if not room:
            raise SystemExit(f"cannot keep {CAPPED_OPERATOR} at a third for {d} in stratum {s}")
        low = min(alloc[(s, e)] for e in room)
        e = rng.choice(sorted(x for x in room if alloc[(s, x)] == low))
        alloc[(s, d)] -= 1
        alloc[(s, e)] += 1


def select(bugs: list[dict], quota: dict[str, int], rng: random.Random) -> list[dict]:
    by_cell = defaultdict(list)
    for b in bugs:
        by_cell[(stratum(b), b["design"])].append(b)
    alloc = {}
    for s in STRATA:
        avail = {d: len(v) for (st, d), v in by_cell.items() if st == s}
        alloc.update({(s, d): n for d, n in water_fill(avail, quota[s], rng).items()})
    rebalance(alloc, by_cell, rng)
    # wrong_signal budget per design = a third of that design's picks across all strata; each
    # cell may use what is left after reserving what the design's other cells are forced to take
    nonws = {k: sum(b["operator"] != CAPPED_OPERATOR for b in v) for k, v in by_cell.items()}
    design_total = Counter()
    for (s, d), n in alloc.items():
        design_total[d] += n
    ws_left = {d: n // 3 for d, n in design_total.items()}
    pending = {k for k, n in alloc.items() if n}
    picked = []
    for key in sorted(pending):
        pending.discard(key)
        reserve = sum(max(0, alloc[k] - nonws[k]) for k in pending if k[1] == key[1])
        got = draw(by_cell[key], alloc[key], ws_left[key[1]] - reserve, rng)
        ws_left[key[1]] -= sum(b["operator"] == CAPPED_OPERATOR for b in got)
        picked += got
    return sorted(picked, key=lambda b: b["id"])


def entry(b: dict) -> dict:
    return {"id": b["id"], "design": b["design"], "stratum": stratum(b), "family": b["family"],
            "operator": b["operator"], "depth_bin": b["formal"]["depth_bin"],
            "depth_exact": b["formal"]["depth_exact"], "file": b["file"], "buggy_sha256": b["buggy_sha256"]}


def build_sets() -> tuple[dict, dict]:
    bugs, manifest_sha = load_manifest()
    rng = random.Random(SEED)
    ev = select(bugs, EVAL_QUOTA, rng)
    taken = {b["id"] for b in ev}
    dev = select([b for b in bugs if b["id"] not in taken], DEV_QUOTA, rng)
    head = {"seed": SEED, "manifest_sha256": manifest_sha, "pool_size": len(bugs)}
    return ({**head, "set": "eval", "size": len(ev), "bugs": [entry(b) for b in ev]},
            {**head, "set": "dev", "size": len(dev), "bugs": [entry(b) for b in dev]})


def report(ev: dict, dev: dict, pool: list[dict]) -> str:
    L = ["# Evaluation subset (Phase 3b)", "",
         "Generated by `make subset` (mutator/subset.py) from bugs/manifest.jsonl "
         f"(sha256 `{ev['manifest_sha256'][:16]}…`, {ev['pool_size']} bugs), seed {ev['seed']}.",
         "", "- **eval_set.json** (frozen, " + str(ev["size"]) + " bugs): the only bugs reported results come from.",
         "- **dev_set.json** (" + str(dev["size"]) + " bugs, disjoint): for building and tuning the agent and baseline prompts.",
         "",
         "Stratified by kind and minimum counterexample depth from reset; within a stratum the quota",
         "is spread over designs as evenly as their bug counts allow, and `wrong_signal` is at most a",
         "third of each design's picks. Families are reported, not given quotas.", ""]
    pool_by = Counter(stratum(b) for b in pool)
    for name, s in (("Eval set", ev), ("Dev set", dev)):
        bs = s["bugs"]
        L += [f"## {name}", "", "| Stratum | Pool | Picked | Designs | Max per design |", "|---|---|---|---|---|"]
        for st in STRATA:
            c = Counter(b["design"] for b in bs if b["stratum"] == st)
            L.append(f"| {st} | {pool_by[st]} | {sum(c.values())} | {len(c)} | {max(c.values())} |")
        seq = sum(b["stratum"] != "comb-0" for b in bs)
        L += [f"| **total** | {len(pool)} | {len(bs)} | | |", "",
              f"Sequential share: {seq}/{len(bs)} ({100 * seq / len(bs):.0f}%).", ""]
        designs = sorted({b["design"] for b in bs})
        L += ["| Design | " + " | ".join(STRATA) + " | total | wrong_signal |",
              "|---|" + "---|" * (len(STRATA) + 2)]
        for d in designs:
            row = [sum(b["design"] == d and b["stratum"] == st for b in bs) for st in STRATA]
            ws = sum(b["design"] == d and b["operator"] == CAPPED_OPERATOR for b in bs)
            L.append(f"| {d} | " + " | ".join(str(x) for x in row) + f" | {sum(row)} | {ws} |")
        L.append("")
        fams = sorted({b["family"] for b in pool})
        L += ["| Family | " + " | ".join(STRATA) + " | total | pool share | picked share |",
              "|---|" + "---|" * (len(STRATA) + 3)]
        pool_f = Counter(b["family"] for b in pool)
        for f in fams:
            row = [sum(b["family"] == f and b["stratum"] == st for b in bs) for st in STRATA]
            L.append(f"| {f} | " + " | ".join(str(x) for x in row) +
                     f" | {sum(row)} | {100 * pool_f[f] / len(pool):.0f}% | {100 * sum(row) / len(bs):.0f}% |")
        ops = Counter(b["operator"] for b in bs)
        L += ["", "Operators: " + ", ".join(f"{o} {n}" for o, n in ops.most_common()) + ".", ""]
    ids = {b["id"] for b in ev["bugs"]}
    missed = [b["id"] for b in pool if b["id"] in ids and not b["reference_test_detected"]]
    inexact = [b["id"] for b in pool if b["id"] in ids and not b["formal"]["depth_exact"]]
    L += ["## Notes", "",
          f"- Eval bugs the hidden reference test misses: {len(missed)}" + (f" ({', '.join(missed)})." if missed else "."),
          f"- Eval bugs whose depth is a BMC bound, not exact: {len(inexact)}" + (f" ({', '.join(inexact)})." if inexact else "."),
          "- Sequential Bit-vector bugs are scarce in the pool, so per-family claims on sequential designs are weak.",
          "",
          "## Evaluation protocol (Phase 6)", "",
          "- Each eval bug is run 3 times for both the agent and the single-shot baseline (LLM output varies).",
          "- Agent vs baseline is compared on the same bugs with McNemar's test (paired: only bugs where they disagree carry information).",
          "- The eval set is frozen: `make subset` will not overwrite it without FORCE=1. Prompts are tuned on the dev set only.",
          "- Grading runs with limited parallelism; an INCONCLUSIVE verdict is re-run once on an idle machine.",
          ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="overwrite an existing frozen eval set")
    args = ap.parse_args()
    if (BUGS / "eval_set.json").exists() and not args.force:
        sys.exit("bugs/eval_set.json exists and is frozen; rerun with --force (make subset FORCE=1) to replace it")
    ev, dev = build_sets()
    pool, _ = load_manifest()
    (BUGS / "eval_set.json").write_text(json.dumps(ev, indent=1) + "\n")
    (BUGS / "dev_set.json").write_text(json.dumps(dev, indent=1) + "\n")
    (BUGS / "SUBSET.md").write_text(report(ev, dev, pool))
    print(f"eval {ev['size']} bugs, dev {dev['size']} bugs; see bugs/SUBSET.md")


if __name__ == "__main__":
    main()
