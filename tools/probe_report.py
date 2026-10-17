"""Phase 6c: the difficulty-probe table (single-shot baseline, model x single/three bugs).

Reads the baseline summaries of each cell and writes bugs/multi/PROBE.md. The decision rule was
fixed before any probe ran: the cheapest cell whose baseline repair rate is 20-60% becomes the new
benchmark setting; if none is, the next probe is larger designs.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CELLS = [  # (model label, bugs label, summary)
    ("Sonnet 5.5", "single (dev 30)", "runs/pilot/summary.json"),
    ("Sonnet 5.5", "three bugs (probe 30)", "runs/probe/sonnet-multi/summary.json"),
    ("Haiku 5.5", "single (dev 30)", "runs/probe/haiku-single/summary.json"),
    ("Haiku 5.5", "three bugs (probe 30)", "runs/probe/haiku-multi/summary.json"),
]
LOW, HIGH = 0.20, 0.60


def main():
    rows, picks = [], []
    for model, bugs, path in CELLS:
        p = ROOT / path
        if not p.exists():
            rows.append(f"| {model} | {bugs} | not run | | | | |")
            continue
        b = json.loads(p.read_text())["arms"]["baseline"]
        n = b["graded"] or b["runs"]
        rate = b["repair_pass"] / n if n else 0
        in_window = LOW <= rate <= HIGH
        if in_window:
            picks.append((b["cost_per_run_usd"], model, bugs))
        rows.append(f"| {model} | {bugs} | {b['repair_pass']}/{n} ({rate:.0%}) | {b['exact']}/{n} | {b['block']}/{n} "
                    f"| ${b['cost_per_run_usd']:.4f} | {'yes' if in_window else 'no'} |")
    verdict = (f"**Pick: {min(picks)[1]}, {min(picks)[2]}** (cheapest cell in the window)." if picks else
               "**No cell in the 20-60% window** -> next probe: larger designs.")
    md = ["# Phase 6c difficulty probe", "",
          "Single-shot baseline only (the agent was not run), dev designs only. Rule fixed in advance: "
          f"the cheapest cell with baseline repair {LOW:.0%}-{HIGH:.0%} becomes the benchmark setting; the new "
          "eval set is then generated fresh (new seed, bugs never used here).", "",
          "| Model | Bugs | Repair PASS | Exact line | Block | Cost/run | In window |",
          "|---|---|---|---|---|---|---|", *rows, "", verdict, ""]
    (ROOT / "bugs" / "multi" / "PROBE.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
