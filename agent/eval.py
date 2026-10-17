"""Runs the agent and the single-shot baseline over a bug set, in parallel, then grades and sums up.

  .venv/bin/python -m agent.eval --set dev --repeats 1 --out runs/pilot     (`make agent-pilot`)
  .venv/bin/python -m agent.eval --set eval --repeats 3 --out runs/eval

Arms: agent, baseline, and bestof (k baseline candidates + a selector on the baseline model, with
k and temperature from config.json's bestof section, which must be tuned on dev first unless
--bestof-k / --bestof-temp override it).

Each run is <out>/<arm>-<bug>-r<k>/. Resumable: a run with an llm.json is kept (rerun errored
runs with --retry-errors), and a half-finished run directory is deleted and redone. After the runs,
every run is graded in the container (tools/grade_runs.py) and <out>/summary.json gets per-arm
outcomes, tokens and cost, plus the cost projected for the full eval (180 bugs x 3 runs per arm).
Spends money: needs OPENROUTER_API_KEY (environment or .env).
"""

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from agent.baseline import run_baseline, run_bestof
from agent.llm import LLMError, OpenRouter, load_config, load_env_file
from agent.run_agent import run_agent
from toolserver.sandbox import IMAGE, remove_leftovers, repo_mount
from toolserver.server import load_bug

ROOT = Path(__file__).resolve().parent.parent
FULL_EVAL_RUNS = 180 * 3
# Grading needs no network, and repo_mount hides .env from the container.
DOCKER = ["docker", "run", "--rm", "--network", "none", *repo_mount(ROOT), IMAGE]


def load_set(path: Path) -> list[dict]:
    return [load_bug(b["id"]) for b in json.loads(Path(path).read_text())["bugs"]]


def finished(run_dir: Path, retry_errors: bool) -> bool:
    try:
        info = json.loads((run_dir / "llm.json").read_text())
    except (OSError, ValueError):
        return False
    return info.get("status") == "done" or not retry_errors


async def one(arm: str, bug: dict, run_dir: Path, cfg: dict, sem) -> dict:
    async with sem:
        if run_dir.exists():
            shutil.rmtree(run_dir)
        if arm == "bestof":
            b = cfg["bestof"]
            llm = OpenRouter(cfg["baseline_model"], b["temperature"], cfg["max_output_tokens"], cfg["prompt_cache"])
            selector = llm.fork(b["selector_temperature"], b.get("selector_model") or cfg["baseline_model"])
            info = await run_bestof(bug, run_dir, llm, selector, b["k"])
        else:
            llm = OpenRouter(cfg[f"{arm}_model"], cfg["temperature"], cfg["max_output_tokens"], cfg["prompt_cache"])
            info = await (run_agent(bug, run_dir, llm, cfg) if arm == "agent" else run_baseline(bug, run_dir, llm))
        print(f"{run_dir.name:<44} {info['stop_reason'] or '-':<18} ${info['cost_usd']:.4f}", flush=True)
        return info


async def drive(jobs, cfg, workers):
    sem = asyncio.Semaphore(workers)
    return await asyncio.gather(*(one(arm, bug, d, cfg, sem) for arm, bug, d in jobs))


def load_grades(path: Path) -> dict:
    return {g["run"]: g for g in json.loads(path.read_text())} if path.exists() else {}


def summarize(out: Path) -> dict:
    infos = [json.loads(p.read_text()) for p in sorted(out.glob("*/llm.json"))]
    grades = load_grades(out / "grades.json")
    cand_grades = load_grades(out / "candidate_grades.json")
    arms = {}
    for arm in sorted({i["arm"] for i in infos}):
        runs = [(p.parent.name, json.loads(p.read_text())) for p in sorted(out.glob(f"{arm}-*/llm.json"))]
        n = len(runs)
        cost = sum(i["cost_usd"] for _, i in runs)
        g = [grades[r] for r, _ in runs if r in grades]
        arms[arm] = {
            "runs": n,
            "states": dict(Counter(i["state"] for _, i in runs)),
            "stop_reasons": dict(Counter(i["stop_reason"] for _, i in runs)),
            "errors": sum(i["status"] == "error" for _, i in runs),
            "repair_pass": sum(x["repair"] == "PASS" for x in g),
            "exact": sum(x["exact"] for x in g),
            "block": sum(x["block"] for x in g),
            "graded": len(g),
            "tokens": sum(i["prompt_tokens"] + i["completion_tokens"] for _, i in runs),
            "cached_tokens": sum(i["cached_tokens"] for _, i in runs),
            "cost_usd": round(cost, 4),
            "cost_per_run_usd": round(cost / n, 4) if n else None,
            "projected_full_eval_usd": round(cost / n * FULL_EVAL_RUNS, 2) if n else None,
        }
        if arm == "bestof" and n:
            # Diagnostic only, never the arm's score: did any candidate pass (an oracle selector)?
            any_pass = sum(any(cand_grades.get(f"{r}/c{c['i']}", {}).get("repair") == "PASS" for c in i["candidates"])
                           for r, i in runs)
            arms[arm] |= {
                "k": runs[0][1]["k"], "temperature": runs[0][1]["temperature"],
                "distinct_candidates_mean": round(sum(i["distinct_candidates"] for _, i in runs) / n, 2),
                "selector_calls": sum(i["selector"]["called"] for _, i in runs),
                "selector_fallbacks": sum(i["selector"]["fallback"] for _, i in runs),
                "selector_cost_usd": round(sum(i["selector"]["cost_usd"] for _, i in runs), 4),
                "any_candidate_pass": any_pass if cand_grades else None,
            }
    return arms


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--set", choices=["dev", "eval"], default="dev")
    ap.add_argument("--bugs", type=Path, help="a bug set file ({\"bugs\": [{\"id\": ...}]}) instead of --set")
    ap.add_argument("--agent-model", help="override agent_model from agent/config.json")
    ap.add_argument("--baseline-model", help="override baseline_model from agent/config.json")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--arms", default="agent,baseline", help="comma list of agent, baseline, bestof")
    ap.add_argument("--bestof-k", type=int, help="override bestof.k (dev tuning only)")
    ap.add_argument("--bestof-temp", type=float, help="override bestof.temperature (dev tuning only)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, help="only the first N bugs of the set")
    ap.add_argument("--out", type=Path, help="default runs/<set>")
    ap.add_argument("--retry-errors", action="store_true")
    ap.add_argument("--no-grade", action="store_true")
    a = ap.parse_args()
    load_env_file()
    cfg = load_config()
    cfg["agent_model"] = a.agent_model or cfg["agent_model"]
    cfg["baseline_model"] = a.baseline_model or cfg["baseline_model"]
    set_file = a.bugs.resolve() if a.bugs else ROOT / "bugs" / f"{a.set}_set.json"
    out = (a.out or Path("runs") / (set_file.stem if a.bugs else a.set)).resolve()
    if not out.is_relative_to(ROOT):
        sys.exit("--out must be inside the repository (grading mounts it into the container)")
    arms = [x for x in a.arms.split(",") if x]
    if set(arms) - {"agent", "baseline", "bestof"}:
        sys.exit("--arms takes agent, baseline and/or bestof")
    if a.bestof_k is not None:
        cfg["bestof"]["k"] = a.bestof_k
    if a.bestof_temp is not None:
        cfg["bestof"]["temperature"] = a.bestof_temp
    if "bestof" in arms and a.bestof_k is None and a.bestof_temp is None and not cfg["bestof"].get("tuned"):
        sys.exit("bestof's k and temperature are not tuned yet: run `make bestof-tune` on dev first")
    bugs = load_set(set_file)[:a.limit]
    out.mkdir(parents=True, exist_ok=True)

    jobs = [(arm, bug, out / f"{arm}-{bug['id']}-r{k}") for bug in bugs for k in range(1, a.repeats + 1)
            for arm in arms]
    todo = [j for j in jobs if not finished(j[2], a.retry_errors)]
    print(f"{len(jobs)} runs, {len(jobs) - len(todo)} already done, {len(todo)} to run "
          f"({a.workers} at a time; agent {cfg['agent_model']}, baseline {cfg['baseline_model']}"
          + (f", bestof k={cfg['bestof']['k']} T={cfg['bestof']['temperature']}" if "bestof" in arms else "") + ")",
          flush=True)
    if todo:
        try:
            info = OpenRouter(cfg["agent_model" if arms[0] == "agent" else "baseline_model"], cfg["temperature"], 1).check_key()
        except LLMError as e:
            sys.exit(f"OpenRouter check failed, nothing was run: {e}")
        left = info.get("limit_remaining")
        print("OpenRouter key OK; " + (f"${left:.2f} left under the key's credit limit" if left is not None
                                       else "no credit limit set on this key"), flush=True)
        if "agent" in arms:
            remove_leftovers()
        asyncio.run(drive(todo, cfg, a.workers))

    if not a.no_grade:
        print("grading in the container...", flush=True)
        g = subprocess.run(DOCKER + ["python", "tools/grade_runs.py", "grade", str(out.relative_to(ROOT))])
        if g.returncode:
            print("grading failed; summary has no grades", file=sys.stderr)
    summary = {"set": str(set_file.relative_to(ROOT)) if set_file.is_relative_to(ROOT) else str(set_file),
               "repeats": a.repeats, "config": cfg, "arms": summarize(out)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["arms"], indent=2))


if __name__ == "__main__":
    main()
