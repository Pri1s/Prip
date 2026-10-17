"""Runs the agent and the single-shot baseline over a bug set, in parallel, then grades and sums up.

  .venv/bin/python -m agent.eval --set dev --repeats 1 --out runs/pilot     (`make agent-pilot`)
  .venv/bin/python -m agent.eval --set eval --repeats 3 --out runs/eval

Each run is <out>/<arm>-<bug>-r<k>/. Resumable: a run with an llm.json is kept (rerun errored
runs with --retry-errors), and a half-finished run directory is deleted and redone. After the runs,
every run is graded in the container (tools/grade_runs.py) and <out>/summary.json gets per-arm
outcomes, tokens and cost, plus the cost projected for the full eval (180 bugs x 3 runs per arm).
Spends money: needs OPENROUTER_API_KEY.
"""

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from agent.baseline import run_baseline
from agent.llm import OpenRouter, load_config
from agent.run_agent import run_agent
from toolserver.sandbox import IMAGE, remove_leftovers
from toolserver.server import load_bug

ROOT = Path(__file__).resolve().parent.parent
FULL_EVAL_RUNS = 180 * 3
DOCKER = ["docker", "run", "--rm", "-v", f"{ROOT}:/work", "-w", "/work", IMAGE]


def load_set(name: str) -> list[dict]:
    return [load_bug(b["id"]) for b in json.loads((ROOT / "bugs" / f"{name}_set.json").read_text())["bugs"]]


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
        model = cfg[f"{arm}_model"]
        llm = OpenRouter(model, cfg["temperature"], cfg["max_output_tokens"], cfg["prompt_cache"])
        info = await (run_agent(bug, run_dir, llm, cfg) if arm == "agent" else run_baseline(bug, run_dir, llm))
        print(f"{run_dir.name:<44} {info['stop_reason'] or '-':<18} ${info['cost_usd']:.4f}", flush=True)
        return info


async def drive(jobs, cfg, workers):
    sem = asyncio.Semaphore(workers)
    return await asyncio.gather(*(one(arm, bug, d, cfg, sem) for arm, bug, d in jobs))


def summarize(out: Path) -> dict:
    infos = [json.loads(p.read_text()) for p in sorted(out.glob("*/llm.json"))]
    grades = {g["run"]: g for g in json.loads((out / "grades.json").read_text())} if (out / "grades.json").exists() else {}
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
    return arms


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--set", choices=["dev", "eval"], default="dev")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--arms", default="agent,baseline")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, help="only the first N bugs of the set")
    ap.add_argument("--out", type=Path, help="default runs/<set>")
    ap.add_argument("--retry-errors", action="store_true")
    ap.add_argument("--no-grade", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    out = (a.out or Path("runs") / a.set).resolve()
    if not out.is_relative_to(ROOT):
        sys.exit("--out must be inside the repository (grading mounts it into the container)")
    arms = [x for x in a.arms.split(",") if x]
    if set(arms) - {"agent", "baseline"}:
        sys.exit("--arms takes agent and/or baseline")
    bugs = load_set(a.set)[:a.limit]
    out.mkdir(parents=True, exist_ok=True)

    jobs = [(arm, bug, out / f"{arm}-{bug['id']}-r{k}") for bug in bugs for k in range(1, a.repeats + 1)
            for arm in arms]
    todo = [j for j in jobs if not finished(j[2], a.retry_errors)]
    print(f"{len(jobs)} runs, {len(jobs) - len(todo)} already done, {len(todo)} to run "
          f"({a.workers} at a time; agent {cfg['agent_model']}, baseline {cfg['baseline_model']})", flush=True)
    if todo:
        if "agent" in arms:
            remove_leftovers()
        asyncio.run(drive(todo, cfg, a.workers))

    if not a.no_grade:
        print("grading in the container...", flush=True)
        g = subprocess.run(DOCKER + ["python", "tools/grade_runs.py", "grade", str(out.relative_to(ROOT))])
        if g.returncode:
            print("grading failed; summary has no grades", file=sys.stderr)
    summary = {"set": a.set, "repeats": a.repeats, "config": cfg, "arms": summarize(out)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["arms"], indent=2))


if __name__ == "__main__":
    main()
