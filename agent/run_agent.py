"""One agent run on one bug: an LLM driving the Phase 5 tool server over MCP until it submits.

The loop runs on the host. It starts toolserver.server as an MCP stdio subprocess (which owns the
workspace, sandbox, budget and submission), offers the server's tools to the model as function
tools, and feeds each tool result back. It stops when the run is over on the server side
(submitted / budget exhausted) or when one of its own caps hits: LLM turns, tokens, wall time, too
many replies without a tool call, or an API error that the retry didn't fix.

Everything the model says is logged to <run>/messages.jsonl (Phase 6b judges recognition from it);
<run>/llm.json records the model, settings, why the loop stopped, tokens and cost.

  .venv/bin/python -m agent.run_agent --bug token_bucket_07 --runs-dir runs
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.client.stdio import get_default_environment

from agent.llm import KEY_VAR, LLMError, OpenRouter, load_config
from agent.prompts import agent_messages
from toolserver.server import MAX_CALLS, MAX_SECONDS, load_bug

ROOT = Path(__file__).resolve().parent.parent
NUDGE = "Continue with the tools. The run only counts once you call submit_patch."


def server_env() -> dict:
    """The tool server's environment: the MCP SDK's safe default, and never the API key."""
    env = get_default_environment()
    env.pop(KEY_VAR, None)
    return env


def to_function_tools(tools) -> list[dict]:
    return [{"type": "function", "function": {"name": t.name, "description": t.description or "",
                                              "parameters": t.input_schema}} for t in tools]


class Log:
    def __init__(self, path: Path):
        self.path = path

    def write(self, turn: int, entry: dict):
        with open(self.path, "a") as f:
            f.write(json.dumps({"turn": turn, **entry}) + "\n")


async def call_tool(client, names: set[str], tc: dict) -> str:
    fn = tc.get("function") or {}
    name = fn.get("name")
    if name not in names:
        return f"ERROR: there is no tool {name!r}; the tools are {', '.join(sorted(names))}"
    try:
        args = json.loads(fn.get("arguments") or "{}")
        if not isinstance(args, dict):
            raise ValueError
    except ValueError:
        return "ERROR: the tool arguments were not a valid JSON object; nothing was run"
    r = await client.call_tool(name, args)
    text = "\n".join(getattr(c, "text", "") for c in r.content)
    return f"ERROR: {text}" if r.is_error else text


def run_state(run_dir: Path) -> str:
    try:
        return json.loads((run_dir / "run.json").read_text())["state"]
    except (OSError, ValueError, KeyError):
        return "unknown"


async def run_agent(bug: dict, run_dir: Path, llm: OpenRouter, cfg: dict, server_args: list[str] = (),
                    max_seconds: float = MAX_SECONDS) -> dict:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True)
    log = Log(run_dir / "messages.jsonl")
    t0 = time.time()
    stop, error, turn = None, None, 0
    params = StdioServerParameters(command=sys.executable, cwd=str(ROOT), env=server_env(), args=[
        "-m", "toolserver.server", "--bug", bug["id"], "--runs-dir", str(run_dir.parent),
        "--run-id", run_dir.name, *server_args])
    try:
        async with Client(params) as client:
            tools = (await client.list_tools()).tools
            names = {t.name for t in tools}
            fn_tools = to_function_tools(tools)
            messages = agent_messages(client.instructions or "", bug)
            for m in messages:
                log.write(0, m)
            nudges = 0
            while True:
                if turn >= cfg["max_turns"]:
                    stop = "turn_cap"
                    break
                if llm.usage.total >= cfg["max_run_tokens"]:
                    stop = "token_cap"
                    break
                if time.time() - t0 > max_seconds:
                    stop = "time"
                    break
                turn += 1
                try:
                    resp = await llm.complete(messages, fn_tools)
                except LLMError as e:
                    stop, error = "api_error", str(e)
                    break
                msg = resp["message"]
                calls = [{"id": tc.get("id") or f"call_{turn}_{i}", "type": "function",
                          "function": tc.get("function") or {}}
                         for i, tc in enumerate(msg.get("tool_calls") or [])]
                assistant = {"role": "assistant", "content": msg.get("content") or (None if calls else "(no reply)")}
                if calls:
                    assistant["tool_calls"] = calls
                messages.append(assistant)
                log.write(turn, {**assistant, "finish_reason": resp["finish_reason"], "usage": resp["usage"]})
                if not calls:
                    if nudges >= cfg["max_nudges"]:
                        stop = "no_tool_calls"
                        break
                    nudges += 1
                    messages.append({"role": "user", "content": NUDGE})
                    log.write(turn, messages[-1])
                    continue
                nudges = 0
                for tc in calls:
                    text = await call_tool(client, names, tc)
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": text})
                    log.write(turn, messages[-1])
                if (state := run_state(run_dir)) != "running":
                    stop = state
                    break
    except Exception as e:  # the tool server died or MCP broke: record it, don't lose the run
        stop, error = "tool_server_error", f"{type(e).__name__}: {e}"

    info = {"arm": "agent", "bug": bug["id"], "model": llm.model, "temperature": llm.temperature,
            "prompt_cache": llm.cache, "stop_reason": stop, "error": error, "state": run_state(run_dir),
            "turns": turn, **llm.usage.as_dict(), "elapsed_s": round(time.time() - t0, 1),
            "status": "error" if stop in ("api_error", "tool_server_error") else "done"}
    (run_dir / "llm.json").write_text(json.dumps(info, indent=2) + "\n")
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bug", required=True)
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--run-id")
    ap.add_argument("--model", help="override agent_model from agent/config.json")
    a = ap.parse_args()
    cfg = load_config()
    bug = load_bug(a.bug)
    run_id = a.run_id or f"agent-{bug['id']}-{time.strftime('%Y%m%d-%H%M%S')}"
    llm = OpenRouter(a.model or cfg["agent_model"], cfg["temperature"], cfg["max_output_tokens"], cfg["prompt_cache"])
    info = asyncio.run(run_agent(bug, Path(a.runs_dir) / run_id, llm, cfg,
                                 ["--max-calls", str(MAX_CALLS), "--max-seconds", str(MAX_SECONDS)]))
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
