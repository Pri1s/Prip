"""Agent vs single-shot baseline (and best-of-k) on eval run directories: paired repair outcomes and McNemar.

  .venv/bin/python tools/compare_arms.py runs/eval-haiku [runs/eval-haiku-bestof] [--md bugs/multi_eval/RESULTS.md]

Runs from all given directories are pooled. Pairs are (bug, repeat k): agent-<bug>-r<k> vs
baseline-<bug>-r<k> (and vs bestof-<bug>-r<k>). McNemar's exact test uses only
the discordant pairs (one arm repaired, the other didn't): under "no difference" each is equally
likely to go either way, so the p-value is a two-sided binomial test at 1/2. A per-bug view (the
majority over repeats) is reported too, since repeats of one bug are not independent.
Also reports how the agent used its tools: did it run a test at all, and did any test fail on the
original buggy file (the raw ingredient of Phase 6b's exposure metric; not yet replayed on golden).
For best-of-k: its k and temperature, distinct candidates, selector use, and how often any
candidate passed (what a perfect selector would get; a diagnostic, not the arm's score).
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


ARMS = ("agent", "baseline", "bestof")
LABEL = {"agent": "Agent", "baseline": "Baseline", "bestof": "Best-of-k"}


def load_runs(dirs: list[Path]):
    grades, cand, info = {}, {}, {}
    for d in dirs:
        for f, into in (("grades.json", grades), ("candidate_grades.json", cand)):
            if (d / f).exists():
                into |= {g["run"]: g for g in json.loads((d / f).read_text())}
        info |= {r.name: (json.loads((r / "llm.json").read_text()), r) for r in d.iterdir() if (r / "llm.json").exists()}
    return grades, cand, info


def paired(grades, info, a, b):
    """[(bug, a passed, b passed)] over (bug, repeat) where both arms have a graded run."""
    out = []
    for name in sorted(n for n in info if n.startswith(a + "-")):
        twin = b + name[len(a):]
        if twin in info and name in grades and twin in grades:
            out.append((name[len(a) + 1:].rsplit("-r", 1)[0], grades[name]["repair"] == "PASS",
                        grades[twin]["repair"] == "PASS"))
    return out


def mcnemar_lines(pairs, a, b) -> list[str]:
    only_a = sum(x and not y for _, x, y in pairs)
    only_b = sum(y and not x for _, x, y in pairs)
    per_bug = defaultdict(lambda: ([], []))
    for bug, x, y in pairs:
        per_bug[bug][0].append(x)
        per_bug[bug][1].append(y)
    maj = [(sum(x) * 2 > len(x), sum(y) * 2 > len(y)) for x, y in per_bug.values()]
    mb, mc = sum(x and not y for x, y in maj), sum(y and not x for x, y in maj)
    return [f"McNemar exact, {LABEL[a]} vs {LABEL[b]} (runs): {only_a} vs {only_b} discordant, "
            f"p = {mcnemar_exact(only_a, only_b):.2g}",
            f"McNemar exact, {LABEL[a]} vs {LABEL[b]} (per bug, majority over repeats): {mb} vs {mc} discordant, "
            f"p = {mcnemar_exact(mb, mc):.2g}"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs_dirs", type=Path, nargs="+")
    ap.add_argument("--md", type=Path)
    a = ap.parse_args()
    grades, cand, info = load_runs(a.runs_dirs)
    arms = [arm for arm in ARMS if any(k.startswith(arm + "-") for k in info)]
    of = {arm: {k: v for k, v in info.items() if k.startswith(arm + "-")} for arm in arms}

    pct = lambda x, d: f"{x}/{d} ({x / d:.0%})" if d else "0/0"
    graded = {arm: [k for k in of[arm] if k in grades] for arm in arms}
    cost = {arm: sum(i["cost_usd"] for i, _ in of[arm].values()) for arm in arms}
    per_run = {arm: cost[arm] / max(1, len(of[arm])) for arm in arms}
    model = {arm: next(iter(of[arm].values()))[0]["model"] for arm in arms}
    bugs = {k[len(arm) + 1:].rsplit("-r", 1)[0] for arm in arms for k in of[arm]}
    row = lambda name, f: f"| {name} | " + " | ".join(f(arm) for arm in arms) + " |"
    lines = [
        f"# {' vs '.join(LABEL[x] for x in arms)}: {', '.join(d.name for d in a.runs_dirs)}", "",
        "Models: " + ", ".join(f"{LABEL[x].lower()} `{model[x]}`" for x in arms) + f". {len(bugs)} bugs.", "",
        "| | " + " | ".join(LABEL[x] for x in arms) + " |", "|---" * (len(arms) + 1) + "|",
        row("Repair PASS", lambda x: pct(sum(grades[k]["repair"] == "PASS" for k in graded[x]), len(graded[x]))),
        row("Exact line (any bug's line)", lambda x: pct(sum(grades[k]["exact"] for k in graded[x]), len(of[x]))),
        row("API/format errors", lambda x: str(sum(i["status"] == "error" for i, _ in of[x].values()))),
        row("Cost", lambda x: f"${cost[x]:.2f} (${per_run[x]:.4f}/run)"),
    ]
    if "agent" in arms:
        lines.append(row("Cost per run vs agent", lambda x: f"{per_run[x] / per_run['agent']:.2f}x"))
    lines.append("")

    for other in ("baseline", "bestof"):
        if "agent" not in arms or other not in arms:
            continue
        p = paired(grades, info, "agent", other)
        both = sum(x and y for _, x, y in p)
        only_a = sum(x and not y for _, x, y in p)
        only_o = sum(y and not x for _, x, y in p)
        lines += [f"**Paired runs, agent vs {LABEL[other].lower()}** (bug, repeat; {len(p)} pairs):", "",
                  f"| | {LABEL[other]} PASS | {LABEL[other]} FAIL |", "|---|---|---|",
                  f"| **Agent PASS** | {both} | {only_a} |",
                  f"| **Agent FAIL** | {only_o} | {len(p) - both - only_a - only_o} |", "",
                  *mcnemar_lines(p, "agent", other), ""]
    if "baseline" in arms and "bestof" in arms:
        lines += mcnemar_lines(paired(grades, info, "bestof", "baseline"), "bestof", "baseline") + [""]

    if "bestof" in arms:
        named = list(of["bestof"].items())
        runs = [v for _, v in named]
        ks = sorted({i["k"] for i, _ in runs})
        temps = sorted({i["temperature"] for i, _ in runs})
        any_pass = sum(any(cand.get(f"{r}/c{c['i']}", {}).get("repair") == "PASS" for c in i["candidates"])
                       for r, (i, _) in named)
        sel_cost = sum(i["selector"]["cost_usd"] for i, _ in runs)
        lines += ["**Best-of-k**:", "",
                  f"- k = {ks}, candidate temperature = {temps}, selector `{runs[0][0]['selector']['model']}` "
                  f"at temperature {runs[0][0]['selector']['temperature']}",
                  f"- distinct candidates per run: mean {sum(i['distinct_candidates'] for i, _ in runs) / len(runs):.2f}",
                  f"- selector called in {sum(i['selector']['called'] for i, _ in runs)}/{len(runs)} runs "
                  f"({sum(i['selector']['fallback'] for i, _ in runs)} fell back to candidate 1); "
                  f"selector cost ${sel_cost:.4f} of ${cost['bestof']:.4f}",
                  f"- any candidate passed (perfect-selector diagnostic, not a score): "
                  + (pct(any_pass, len(runs)) if cand else "not graded"), ""]

    if "agent" in arms:
        agents = graded["agent"]
        use = [agent_tool_use(info[r][1]) for r in agents]
        stops = defaultdict(int)
        for r in agents:
            stops[info[r][0]["stop_reason"]] += 1
        lines += ["**Agent tool use**:", "",
                  f"- ran at least one cocotb test: {pct(sum(u['ran_test'] for u in use), len(use))}",
                  f"- had a test fail on the original buggy file: {pct(sum(u['failing_on_original'] for u in use), len(use))}",
                  f"- tool calls per run: mean {sum(u['calls'] for u in use) / max(1, len(use)):.1f}",
                  f"- stop reasons: {dict(stops)}", ""]
    text = "\n".join(lines)
    print(text)
    if a.md:
        a.md.write_text(text)


if __name__ == "__main__":
    main()
