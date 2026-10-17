"""One single-shot baseline run: the same model and inputs as the agent, no tools, one reply.

The model answers with JSON {line, explanation, patched_file, test?}. The run directory uses the
tool server's layout (run.json, submission/<top>.v, submission/submission.json, submission/tests/),
so tools/grade_runs.py grades baseline and agent runs the same way. An optional test is kept for
Phase 6b's exposure replay; recognition doesn't apply (the baseline never sees a test fail).

An API error or an unusable reply is retried once; if the retry fails too the run has no
submission (a failure) and llm.json says why.

Best-of-k (`--k`, Phase 6d's cost-matched control): k independent baseline runs under
candidates/c<i>/, then a selector call picks one and its submission becomes the run's submission.
The selector sees only what the baseline saw (spec, numbered buggy RTL) plus each candidate's
blamed line, explanation and diff against the buggy file: no golden file, hidden test, simulation,
lint or formal result. Candidates identical up to whitespace count once; with one distinct
candidate there is no selector call. An unusable selector reply is retried once, then candidate
1 is used. Cost and tokens in llm.json are the sum over candidates and the selector.

  .venv/bin/python -m agent.baseline --bug token_bucket_07 --runs-dir runs [--k 3 --temperature 0.7]
"""

import argparse
import asyncio
import difflib
import hashlib
import json
import random
import re
import shutil
import time
from pathlib import Path

from agent.llm import LLMError, OpenRouter, load_config, load_env_file
from agent.prompts import baseline_messages, selector_messages
from toolserver.server import load_bug
from toolserver.workspace import MAX_FILE_BYTES

ROOT = Path(__file__).resolve().parent.parent
MAX_EXPLANATION = 4000


class BadReply(Exception):
    pass


def parse_reply(text: str) -> dict:
    """The JSON object in the reply (bare, or inside a ``` fence). Raises BadReply."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"):text.rfind("}") + 1]
    try:
        obj = json.loads(raw)
    except ValueError:
        raise BadReply("reply is not a JSON object")
    if not isinstance(obj, dict):
        raise BadReply("reply is not a JSON object")
    line, patched, test = obj.get("line"), obj.get("patched_file"), obj.get("test")
    if isinstance(line, str) and line.strip().isdigit():
        line = int(line)
    if isinstance(line, bool) or not isinstance(line, int):
        raise BadReply("line is not a number")
    if not isinstance(patched, str) or "module" not in patched:
        raise BadReply("patched_file is not a Verilog file")
    if len(patched.encode()) > MAX_FILE_BYTES:
        raise BadReply("patched_file is too large")
    explanation = obj.get("explanation") if isinstance(obj.get("explanation"), str) else ""
    return {"line": line, "explanation": explanation[:MAX_EXPLANATION], "patched_file": patched,
            "test": test if isinstance(test, str) and test.strip() else None}


async def run_baseline(bug: dict, run_dir: Path, llm: OpenRouter) -> dict:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True)
    t0 = time.time()
    top = bug["top"]
    messages = baseline_messages(bug)
    log = run_dir / "messages.jsonl"
    with open(log, "w") as f:
        for m in messages:
            f.write(json.dumps({"turn": 0, **m}) + "\n")

    reply, errors = None, []
    for attempt in (1, 2):
        try:
            resp = await llm.complete(messages)
            text = resp["message"].get("content") or ""
            with open(log, "a") as f:
                f.write(json.dumps({"turn": attempt, "role": "assistant", "content": text,
                                    "finish_reason": resp["finish_reason"], "usage": resp["usage"]}) + "\n")
            reply = parse_reply(text)
            break
        except (LLMError, BadReply) as e:
            errors.append(f"attempt {attempt}: {type(e).__name__}: {e}")

    state = "no_submission"
    if reply:
        sub = run_dir / "submission"
        (sub / "tests").mkdir(parents=True)
        (sub / f"{top}.v").write_text(reply["patched_file"])
        tests = []
        if reply["test"]:
            (sub / "tests" / "test_baseline.py").write_text(reply["test"])
            tests = ["test_baseline.py"]
        (sub / "submission.json").write_text(json.dumps({
            "bug": bug["id"], "file": f"{top}.v", "line": reply["line"], "explanation": reply["explanation"],
            "patch_sha256": hashlib.sha256(reply["patched_file"].encode()).hexdigest(), "tests": tests,
            "submitted_t": round(time.time() - t0, 2)}, indent=2) + "\n")
        state = "submitted"
    (run_dir / "run.json").write_text(json.dumps({"bug": bug["id"], "top": top, "arm": "baseline",
                                                  "state": state, "started": t0}, indent=2) + "\n")
    info = {"arm": "baseline", "bug": bug["id"], "model": llm.model, "temperature": llm.temperature,
            "prompt_cache": llm.cache, "stop_reason": state, "error": "; ".join(errors) or None,
            "state": state, "turns": llm.usage.calls, **llm.usage.as_dict(),
            "elapsed_s": round(time.time() - t0, 1), "status": "done" if reply else "error"}
    (run_dir / "llm.json").write_text(json.dumps(info, indent=2) + "\n")
    return info


def parse_choice(text: str, n: int) -> int:
    """The selector's candidate number (1..n). Raises BadReply."""
    m = re.search(r"\{.*\}", text, re.S)
    try:
        obj = json.loads(m.group(0)) if m else None
    except ValueError:
        obj = None
    choice = obj.get("choice") if isinstance(obj, dict) else None
    if isinstance(choice, str) and choice.strip().isdigit():
        choice = int(choice)
    if isinstance(choice, bool) or not isinstance(choice, int) or not 1 <= choice <= n:
        raise BadReply(f"choice is not a candidate number 1..{n}")
    return choice


def _norm(text: str) -> str:
    return " ".join(text.split())


async def select(bug: dict, cands: list[dict], selector: OpenRouter, seed: str, log: Path) -> tuple[int, dict]:
    """Picks one of `cands` (distinct, each {"i", "line", "explanation", "patched_file"}). Returns
    (index into cands, record for llm.json)."""
    order = list(range(len(cands)))
    random.Random(seed).shuffle(order)   # no position bias toward candidate 1
    buggy = (ROOT / bug["file"]).read_text().splitlines(keepends=True)
    shown = [{"line": cands[j]["line"], "explanation": cands[j]["explanation"],
              "diff": "".join(difflib.unified_diff(buggy, cands[j]["patched_file"].splitlines(keepends=True),
                                                   f"original/{bug['top']}.v", f"candidate/{bug['top']}.v", n=2))}
             for j in order]
    messages = selector_messages(bug, shown)
    with open(log, "w") as f:
        for m in messages:
            f.write(json.dumps({"turn": 0, **m}) + "\n")
    errors = []
    for attempt in (1, 2):
        try:
            resp = await selector.complete(messages)
            text = resp["message"].get("content") or ""
            with open(log, "a") as f:
                f.write(json.dumps({"turn": attempt, "role": "assistant", "content": text,
                                    "finish_reason": resp["finish_reason"], "usage": resp["usage"]}) + "\n")
            pick = order[parse_choice(text, len(cands)) - 1]
            return pick, {"called": True, "shown_order": [cands[j]["i"] for j in order], "fallback": False,
                          "error": "; ".join(errors) or None}
        except (LLMError, BadReply) as e:
            errors.append(f"attempt {attempt}: {type(e).__name__}: {e}")
    return 0, {"called": True, "shown_order": [cands[j]["i"] for j in order], "fallback": True,
               "error": "; ".join(errors)}


async def run_bestof(bug: dict, run_dir: Path, llm: OpenRouter, selector: OpenRouter, k: int) -> dict:
    """k baseline runs with `llm`'s settings (each on a fork, so usage is per candidate), then
    `selector` picks one. Candidates run one after another so later ones can read the prompt cache."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True)
    t0 = time.time()
    infos, cands, seen = [], [], {}
    for i in range(1, k + 1):
        cdir = run_dir / "candidates" / f"c{i}"
        info = await run_baseline(bug, cdir, llm.fork())
        sub = cdir / "submission" / "submission.json"
        rec = {"i": i, "state": info["state"], "cost_usd": info["cost_usd"], "error": info["error"]}
        if sub.exists():
            s = json.loads(sub.read_text())
            patched = (cdir / "submission" / s["file"]).read_text()
            key = _norm(patched)
            rec |= {"line": s["line"], "patch_sha256": s["patch_sha256"], "same_as": seen.get(key)}
            if key not in seen:
                seen[key] = i
                cands.append({"i": i, "line": s["line"], "explanation": s["explanation"], "patched_file": patched})
        infos.append((rec, info))

    sel = {"called": False, "shown_order": None, "fallback": False, "error": None}
    chosen = None
    if len(cands) == 1:
        chosen = cands[0]["i"]
    elif cands:
        j, sel = await select(bug, cands, selector, run_dir.name, run_dir / "selector.jsonl")
        chosen = cands[j]["i"]
    sel |= {"model": selector.model, "temperature": selector.temperature, **selector.usage.as_dict()}

    state = "no_submission"
    if chosen:
        shutil.copytree(run_dir / "candidates" / f"c{chosen}" / "submission", run_dir / "submission")
        p = run_dir / "submission" / "submission.json"
        s = json.loads(p.read_text())
        s |= {"selected_candidate": chosen, "submitted_t": round(time.time() - t0, 2)}
        p.write_text(json.dumps(s, indent=2) + "\n")
        state = "submitted"
    (run_dir / "run.json").write_text(json.dumps({"bug": bug["id"], "top": bug["top"], "arm": "bestof",
                                                  "state": state, "started": t0}, indent=2) + "\n")
    keys = ("llm_calls", "prompt_tokens", "completion_tokens", "cached_tokens")
    totals = {key: sum(info[key] for _, info in infos) + sel[key] for key in keys}
    totals["cost_usd"] = round(sum(info["cost_usd"] for _, info in infos) + sel["cost_usd"], 6)
    errors = [f"c{rec['i']}: {rec['error']}" for rec, _ in infos if rec["error"]]
    if sel["error"]:
        errors.append(f"selector: {sel['error']}")
    info = {"arm": "bestof", "bug": bug["id"], "model": llm.model, "temperature": llm.temperature, "k": k,
            "prompt_cache": llm.cache, "stop_reason": state, "error": "; ".join(errors) or None, "state": state,
            "turns": totals["llm_calls"], **totals, "distinct_candidates": len(cands), "selected": chosen,
            "candidates": [rec for rec, _ in infos], "selector": sel,
            "elapsed_s": round(time.time() - t0, 1), "status": "done" if chosen else "error"}
    (run_dir / "llm.json").write_text(json.dumps(info, indent=2) + "\n")
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bug", required=True)
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--run-id")
    ap.add_argument("--model", help="override baseline_model from agent/config.json")
    ap.add_argument("--k", type=int, help="best-of-k with a selector (default: one single-shot reply)")
    ap.add_argument("--temperature", type=float, help="candidate temperature for --k (default: config bestof)")
    a = ap.parse_args()
    load_env_file()
    cfg = load_config()
    bug = load_bug(a.bug)
    arm = "bestof" if a.k else "baseline"
    run_dir = Path(a.runs_dir) / (a.run_id or f"{arm}-{bug['id']}-{time.strftime('%Y%m%d-%H%M%S')}")
    model = a.model or cfg["baseline_model"]
    if a.k:
        b = cfg["bestof"]
        llm = OpenRouter(model, b["temperature"] if a.temperature is None else a.temperature,
                         cfg["max_output_tokens"], cfg["prompt_cache"])
        selector = llm.fork(b["selector_temperature"], b.get("selector_model") or model)
        info = asyncio.run(run_bestof(bug, run_dir, llm, selector, a.k))
    else:
        llm = OpenRouter(model, cfg["temperature"], cfg["max_output_tokens"], cfg["prompt_cache"])
        info = asyncio.run(run_baseline(bug, run_dir, llm))
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
