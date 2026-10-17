"""One single-shot baseline run: the same model and inputs as the agent, no tools, one reply.

The model answers with JSON {line, explanation, patched_file, test?}. The run directory uses the
tool server's layout (run.json, submission/<top>.v, submission/submission.json, submission/tests/),
so tools/grade_runs.py grades baseline and agent runs the same way. An optional test is kept for
Phase 6b's exposure replay; recognition doesn't apply (the baseline never sees a test fail).

An API error or an unusable reply is retried once; if the retry fails too the run has no
submission (a failure) and llm.json says why.

  .venv/bin/python -m agent.baseline --bug token_bucket_07 --runs-dir runs
"""

import argparse
import asyncio
import hashlib
import json
import re
import time
from pathlib import Path

from agent.llm import LLMError, OpenRouter, load_config
from agent.prompts import baseline_messages
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bug", required=True)
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--run-id")
    ap.add_argument("--model", help="override baseline_model from agent/config.json")
    a = ap.parse_args()
    cfg = load_config()
    bug = load_bug(a.bug)
    run_id = a.run_id or f"baseline-{bug['id']}-{time.strftime('%Y%m%d-%H%M%S')}"
    llm = OpenRouter(a.model or cfg["baseline_model"], cfg["temperature"], cfg["max_output_tokens"], cfg["prompt_cache"])
    print(json.dumps(asyncio.run(run_baseline(bug, Path(a.runs_dir) / run_id, llm)), indent=2))


if __name__ == "__main__":
    main()
