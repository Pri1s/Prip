"""Agent vs single-shot baseline on one eval run directory: paired repair outcomes and McNemar.

  .venv/bin/python tools/compare_arms.py runs/eval-haiku [--md bugs/multi_eval/RESULTS.md]

Pairs are (bug, repeat k): agent-<bug>-r<k> vs baseline-<bug>-r<k>. McNemar's exact test uses only
the discordant pairs (one arm repaired, the other didn't): under "no difference" each is equally
likely to go either way, so the p-value is a two-sided binomial test at 1/2. A per-bug view (the
majority over repeats) is reported too, since repeats of one bug are not independent.
Also reports how the agent used its tools: did it run a test at all, and did any test fail on the
original buggy file (the raw ingredient of Phase 6b's exposure metric; not yet replayed on golden).
"""

import argparse
import json
from collections import defaultdict
from math import comb
from pathlib import Path


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def agent_tool_use(run_dir: Path) -> dict:
    trace = run_dir / "trace.jsonl"
    entries = [json.loads(l) for l in trace.read_text().splitlines()] if trace.exists() else []
    runs = [e for e in entries if e["tool"] == "run_cocotb" and e.get("ok")]
    fail_orig = any(e["result"].get("target") == "original" and
                    any(not t["passed"] and not t.get("skipped") for t in e["result"].get("tests", []))
                    for e in runs)
    return {"calls": len(entries), "cocotb_runs": len(runs), "ran_test": bool(runs), "failing_on_original": fail_orig}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs_dir", type=Path)
    ap.add_argument("--md", type=Path)
    a = ap.parse_args()
    grades = {g["run"]: g for g in json.loads((a.runs_dir / "grades.json").read_text())}
    info = {d.name: json.loads((d / "llm.json").read_text()) for d in a.runs_dir.iterdir() if (d / "llm.json").exists()}

    pairs, per_bug = [], defaultdict(lambda: {"agent": [], "baseline": []})
    for name in sorted(n for n in info if n.startswith("agent-")):
        twin = "baseline-" + name[len("agent-"):]
        if twin not in info or name not in grades or twin not in grades:
            continue
        bug = name[len("agent-"):].rsplit("-r", 1)[0]
        ag, bl = grades[name]["repair"] == "PASS", grades[twin]["repair"] == "PASS"
        pairs.append((bug, ag, bl))
        per_bug[bug]["agent"].append(ag)
        per_bug[bug]["baseline"].append(bl)

    n = len(pairs)
    both = sum(ag and bl for _, ag, bl in pairs)
    only_agent = sum(ag and not bl for _, ag, bl in pairs)
    only_base = sum(bl and not ag for _, ag, bl in pairs)
    neither = n - both - only_agent - only_base
    maj = {b: (sum(v["agent"]) * 2 > len(v["agent"]), sum(v["baseline"]) * 2 > len(v["baseline"])) for b, v in per_bug.items()}
    mb = sum(ag and not bl for ag, bl in maj.values())
    mc = sum(bl and not ag for ag, bl in maj.values())

    agents = [n for n in info if n.startswith("agent-") and n in grades]
    use = [agent_tool_use(a.runs_dir / r) for r in agents]
    stops = defaultdict(int)
    for r in agents:
        stops[info[r]["stop_reason"]] += 1
    cost = {arm: sum(i["cost_usd"] for k, i in info.items() if k.startswith(arm + "-")) for arm in ("agent", "baseline")}
    runs_of = {arm: sum(1 for k in info if k.startswith(arm + "-")) for arm in ("agent", "baseline")}
    errors = {arm: sum(1 for k, i in info.items() if k.startswith(arm + "-") and i["status"] == "error") for arm in ("agent", "baseline")}
    loc = {arm: sum(g["exact"] for k, g in grades.items() if k.startswith(arm + "-")) for arm in ("agent", "baseline")}
    model = {arm: next((i["model"] for k, i in info.items() if k.startswith(arm + "-")), "?") for arm in ("agent", "baseline")}

    pct = lambda x, d: f"{x}/{d} ({x / d:.0%})" if d else "0/0"
    lines = [
        f"# Agent vs baseline: {a.runs_dir.name}", "",
        f"Models: agent `{model['agent']}`, baseline `{model['baseline']}`. {len(per_bug)} bugs, {n} paired runs.", "",
        "| | Agent | Baseline |", "|---|---|---|",
        f"| Repair PASS | {pct(both + only_agent, n)} | {pct(both + only_base, n)} |",
        f"| Exact line (any bug's line) | {pct(loc['agent'], runs_of['agent'])} | {pct(loc['baseline'], runs_of['baseline'])} |",
        f"| API/format errors | {errors['agent']} | {errors['baseline']} |",
        f"| Cost | ${cost['agent']:.2f} (${cost['agent'] / max(1, runs_of['agent']):.4f}/run) | ${cost['baseline']:.2f} (${cost['baseline'] / max(1, runs_of['baseline']):.4f}/run) |",
        "",
        "**Paired runs** (bug, repeat):", "",
        f"| | Baseline PASS | Baseline FAIL |", "|---|---|---|",
        f"| **Agent PASS** | {both} | {only_agent} |",
        f"| **Agent FAIL** | {only_base} | {neither} |", "",
        f"McNemar exact (runs): {only_agent} vs {only_base} discordant, p = {mcnemar_exact(only_agent, only_base):.4f}",
        f"McNemar exact (per bug, majority over repeats): {mb} vs {mc} discordant, p = {mcnemar_exact(mb, mc):.4f}", "",
        "**Agent tool use**:", "",
        f"- ran at least one cocotb test: {pct(sum(u['ran_test'] for u in use), len(use))}",
        f"- had a test fail on the original buggy file: {pct(sum(u['failing_on_original'] for u in use), len(use))}",
        f"- tool calls per run: mean {sum(u['calls'] for u in use) / max(1, len(use)):.1f}",
        f"- stop reasons: {dict(stops)}", "",
    ]
    text = "\n".join(lines)
    print(text)
    if a.md:
        a.md.write_text(text)


if __name__ == "__main__":
    main()
