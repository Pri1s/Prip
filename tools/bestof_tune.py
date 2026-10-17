"""Phase 6d: picks the best-of-k baseline's temperature and k on the dev set, then freezes them.

Reads runs/bestof-tune/k<k>-t<T>/summary.json (made by `make bestof-tune`, on the 30 dev three-bug
variants in bugs/multi/probe_set.json, Haiku 5.5, one run each), writes bugs/multi/BESTOF_TUNE.md
and, once the rule settles, sets config.json's bestof k / temperature / tuned. The rule was fixed
before any tuning run:

  1. temperature: among k=3 runs at 0.2 / 0.7 / 1.0, the highest repair rate of the SELECTED
     answer; a tie goes to the lower temperature. (The any-candidate rate is shown, never used.)
  2. k: 3 if k=3's mean cost per run at that temperature is <= 1.15 x the agent's eval cost per
     run; otherwise k=2 (measured at that temperature with `make bestof-tune-k2 T=<T>`) if it is
     under the cap; otherwise a cheaper selector is needed and nothing is frozen.

The agent cost is a cost only (runs/eval-haiku: $1.7864 / 360 runs); no eval-set accuracy is used.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TUNE = ROOT / "runs" / "bestof-tune"
CONFIG = ROOT / "agent" / "config.json"
OUT = ROOT / "bugs" / "multi" / "BESTOF_TUNE.md"
TEMPS = (0.2, 0.7, 1.0)
AGENT_COST = 1.7864 / 360
CAP = 1.15 * AGENT_COST


def load(k: int, t: float) -> dict | None:
    p = TUNE / f"k{k}-t{t}" / "summary.json"
    return json.loads(p.read_text())["arms"]["bestof"] if p.exists() else None


def main():
    rows, k3 = [], {}
    for k in (3, 2):
        for t in TEMPS:
            b = load(k, t)
            if not b:
                continue
            if k == 3:
                k3[t] = b
            n = b["graded"] or b["runs"]
            anyp = "-" if b["any_candidate_pass"] is None else f"{b['any_candidate_pass']}/{n}"
            rows.append(f"| {k} | {t} | {b['repair_pass']}/{n} | {anyp} | {b['distinct_candidates_mean']} | "
                        f"{b['selector_calls']} ({b['selector_fallbacks']} fallback) | ${b['cost_per_run_usd']:.4f} | "
                        f"{b['cost_per_run_usd'] / AGENT_COST:.2f}x |")
    missing = [t for t in TEMPS if t not in k3]
    if missing:
        decision, freeze = f"not decided: k=3 runs missing at T = {missing} (`make bestof-tune`)", None
    else:
        t = max(TEMPS, key=lambda x: (k3[x]["repair_pass"], -x))
        if k3[t]["cost_per_run_usd"] <= CAP:
            decision, freeze = f"T = {t}, k = 3 (k=3 cost ${k3[t]['cost_per_run_usd']:.4f} <= cap ${CAP:.4f})", (3, t)
        elif not (k2 := load(2, t)):
            decision, freeze = (f"T = {t}; k=3 costs ${k3[t]['cost_per_run_usd']:.4f} > cap ${CAP:.4f}: "
                                f"run `make bestof-tune-k2 T={t}`"), None
        elif k2["cost_per_run_usd"] <= CAP:
            decision, freeze = f"T = {t}, k = 2 (k=3 over the cap; k=2 ${k2['cost_per_run_usd']:.4f} <= ${CAP:.4f})", (2, t)
        else:
            decision, freeze = f"T = {t}; k=2 still over the cap (${k2['cost_per_run_usd']:.4f}): needs a cheaper selector", None

    lines = ["# Best-of-k baseline tuning (dev, Haiku 5.5, three-bug probe set)", "",
             f"Agent eval cost per run ${AGENT_COST:.4f}; cap = 1.15x = ${CAP:.4f}. Rule: see tools/bestof_tune.py.", "",
             "| k | T | Selected repair | Any candidate (diagnostic) | Distinct cands | Selector calls | Cost/run | vs agent |",
             "|---|---|---|---|---|---|---|---|", *rows, "", f"**Decision:** {decision}", ""]
    OUT.write_text("\n".join(lines))
    print("\n".join(lines))
    if freeze:
        cfg = json.loads(CONFIG.read_text())
        cfg["bestof"] |= {"k": freeze[0], "temperature": freeze[1], "tuned": str(OUT.relative_to(ROOT))}
        CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
        print(f"froze bestof k={freeze[0]} temperature={freeze[1]} in agent/config.json")
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
