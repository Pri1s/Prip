"""Tests for the Phase 6a agent loop, baseline and OpenRouter client, with a fake API (`make agent-test`).

No network and no money: the fake stands in for OpenRouter's HTTP endpoint and replays scripted
replies. Agent tests run the real tool server and sandbox (Docker), like `make tools-test`.
"""

import asyncio
import json
from pathlib import Path

import pytest

from agent import baseline, llm as llm_mod, run_agent as ra
from agent.llm import KEY_VAR, LLMError, OpenRouter
from toolserver.sandbox import remove_leftovers
from toolserver.server import load_bug

ROOT = Path(__file__).resolve().parent.parent
BUG = "token_bucket_07"
SECRET = "sk-or-test-NEVER-WRITE-ME-0123456789"
CFG = {"max_turns": 12, "max_run_tokens": 10**9, "max_nudges": 1}
USAGE = {"prompt_tokens": 1000, "completion_tokens": 100, "prompt_tokens_details": {"cached_tokens": 800},
         "cost": 0.0021}


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv(KEY_VAR, SECRET)


@pytest.fixture(scope="module")
def _clean_sandboxes():
    remove_leftovers()
    yield
    remove_leftovers()


class FakeAPI:
    """Replaces http_post. Each reply is a message dict, a (status, bytes) pair, or a function of
    the request body returning either. The last reply repeats once the script runs out."""

    def __init__(self, *replies, usage=USAGE):
        self.replies, self.usage = list(replies), usage
        self.bodies, self.headers = [], []

    def __call__(self, url, payload, headers, timeout):
        body = json.loads(payload)
        self.bodies.append(body)
        self.headers.append(headers)
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if callable(r):
            r = r(body)
        if isinstance(r, tuple):
            return r
        return 200, json.dumps({"choices": [{"message": r, "finish_reason": "stop"}], "usage": self.usage}).encode()


def tool(name, text="", **args):
    return {"content": text, "tool_calls": [
        {"id": f"c_{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def client(api, model="anthropic/claude-test", **kw):
    return OpenRouter(model, 0.2, 1000, cache=True, post=api, wait_s=0, **kw)


def no_secret_in(d: Path):
    for p in d.rglob("*"):
        if p.is_file():
            assert SECRET not in p.read_text(errors="replace"), p


# -- OpenRouter client -------------------------------------------------------------------------

def test_body_settings_and_cache_breakpoints():
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "u"},
            {"role": "assistant", "content": None, "tool_calls": []}, {"role": "tool", "tool_call_id": "x", "content": "t"}]
    b = client(FakeAPI({})).body(msgs, [{"type": "function"}])
    assert b["temperature"] == 0.2 and b["max_tokens"] == 1000 and b["usage"] == {"include": True}
    assert b["tools"] == [{"type": "function"}]
    assert b["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert b["messages"][-1]["content"][0] == {"type": "text", "text": "t", "cache_control": {"type": "ephemeral"}}
    assert b["messages"][1]["content"] == "u"
    assert msgs[0]["content"] == "sys"   # the caller's messages are not modified
    plain = OpenRouter("openai/gpt-test", 0.2, 1000, post=FakeAPI({})).body(msgs)
    assert "cache_control" not in json.dumps(plain) and "tools" not in plain


def test_key_only_in_header():
    api = FakeAPI({"content": "hi"})
    asyncio.run(client(api).complete([{"role": "user", "content": "x"}]))
    assert api.headers[0]["Authorization"] == f"Bearer {SECRET}"
    assert SECRET not in json.dumps(api.bodies)


def test_missing_key(monkeypatch):
    monkeypatch.delenv(KEY_VAR)
    with pytest.raises(LLMError, match=KEY_VAR):
        OpenRouter("m", 0.2, 10)


def test_retry_once_then_error():
    api = FakeAPI((503, b'{"error": {"message": "overloaded"}}'))
    with pytest.raises(LLMError, match="overloaded"):
        asyncio.run(client(api).complete([{"role": "user", "content": "x"}]))
    assert len(api.bodies) == 2

    api = FakeAPI((429, b"{}"), {"content": "ok"})
    c = client(api)
    r = asyncio.run(c.complete([{"role": "user", "content": "x"}]))
    assert r["message"]["content"] == "ok" and len(api.bodies) == 2
    assert c.usage.as_dict() == {"llm_calls": 1, "prompt_tokens": 1000, "completion_tokens": 100,
                                 "cached_tokens": 800, "cost_usd": 0.0021}

    api = FakeAPI((400, b'{"error": {"message": "bad request"}}'))
    with pytest.raises(LLMError):
        asyncio.run(client(api).complete([{"role": "user", "content": "x"}]))
    assert len(api.bodies) == 1   # not retryable


def test_server_env_has_no_key():
    assert KEY_VAR not in ra.server_env()


# -- baseline ----------------------------------------------------------------------------------

GOLDEN = (ROOT / "designs" / "token_bucket" / "golden.v").read_text()


def reply(**over):
    obj = {"line": 12, "explanation": "refill compares with < instead of <=", "patched_file": GOLDEN,
           "test": "import cocotb\n@cocotb.test()\nasync def t(dut):\n    pass\n"}
    obj.update(over)
    return {"content": "```json\n" + json.dumps(obj) + "\n```"}


def test_parse_reply():
    r = baseline.parse_reply(reply(line="7", test="")["content"])
    assert r["line"] == 7 and r["test"] is None
    assert baseline.parse_reply(json.dumps({"line": 3, "patched_file": "module m; endmodule"}))["line"] == 3
    for bad in ("no json here", json.dumps({"line": "x", "patched_file": GOLDEN}),
                json.dumps({"line": 3, "patched_file": "not verilog"}), "[1, 2]"):
        with pytest.raises(baseline.BadReply):
            baseline.parse_reply(bad)


def test_baseline_writes_submission(tmp_path):
    api = FakeAPI(reply())
    bug = load_bug(BUG)
    info = asyncio.run(baseline.run_baseline(bug, tmp_path / "b", client(api)))
    d = tmp_path / "b"
    assert info["state"] == "submitted" and info["status"] == "done" and info["cost_usd"] == 0.0021
    sub = json.loads((d / "submission" / "submission.json").read_text())
    assert sub["line"] == 12 and sub["file"] == "token_bucket.v" and sub["tests"] == ["test_baseline.py"]
    assert (d / "submission" / "token_bucket.v").read_text() == GOLDEN
    assert json.loads((d / "run.json").read_text())["state"] == "submitted"
    assert "tools" not in api.bodies[0]
    user = api.bodies[0]["messages"][1]["content"]
    user = user if isinstance(user, str) else user[0]["text"]
    assert " 1| " in user and "spec" in user   # same numbered context the agent gets
    no_secret_in(d)


def test_baseline_bad_reply_retried_then_fails(tmp_path):
    api = FakeAPI({"content": "I think line 12 is wrong."})
    info = asyncio.run(baseline.run_baseline(load_bug(BUG), tmp_path / "b", client(api)))
    assert len(api.bodies) == 2
    assert info["state"] == "no_submission" and info["status"] == "error" and "attempt 2" in info["error"]
    assert not (tmp_path / "b" / "submission").exists()


def test_baseline_retry_succeeds(tmp_path):
    api = FakeAPI({"content": "oops"}, reply())
    info = asyncio.run(baseline.run_baseline(load_bug(BUG), tmp_path / "b", client(api)))
    assert info["state"] == "submitted" and info["status"] == "done" and len(api.bodies) == 2


# -- agent loop (real tool server + sandbox) ---------------------------------------------------

def last_tool_text(body) -> str:
    m = body["messages"][-1]
    assert m["role"] == "tool"
    return m["content"] if isinstance(m["content"], str) else m["content"][0]["text"]


def agent(tmp_path, api, server_args=(), cfg=CFG):
    return asyncio.run(ra.run_agent(load_bug(BUG), tmp_path / "a", client(api), cfg, list(server_args)))


def test_agent_round_trip(tmp_path, _clean_sandboxes):
    bug = load_bug(BUG)
    ref = (ROOT / "designs" / "token_bucket" / "ref_test.py").read_text()
    line = bug["localization"]["buggy_lines"][0]
    seen = {}

    def after_run(body):
        seen["run"] = last_tool_text(body)
        return tool("write_file", "The test fails on the original, so the design is wrong; fixing it.",
                    path="token_bucket.v", content=GOLDEN)

    api = FakeAPI(
        tool("write_file", "I'll write a test from the spec.", path="tests/test_spec.py", content=ref),
        tool("run_cocotb", "Run it on the original.", test_file="tests/test_spec.py", target="original"),
        after_run,
        tool("submit_patch", "Submitting.", line=line, explanation="fixed"),
    )
    info = agent(tmp_path, api)
    d = tmp_path / "a"
    assert info["stop_reason"] == "submitted" and info["state"] == "submitted" and info["status"] == "done"
    assert info["turns"] == 4 and info["llm_calls"] == 4 and info["cost_usd"] == pytest.approx(4 * 0.0021)
    assert "failed" in seen["run"] and "budget left" in seen["run"]
    sub = json.loads((d / "submission" / "submission.json").read_text())
    assert sub["line"] == line and (d / "submission" / "token_bucket.v").read_text() == GOLDEN

    first = api.bodies[0]
    assert {t["function"]["name"] for t in first["tools"]} == {
        "read_file", "write_file", "lint", "run_cocotb", "submit_patch"}
    assert "submit_patch" in first["messages"][0]["content"][0]["text"]   # server instructions in system prompt
    log = [json.loads(l) for l in (d / "messages.jsonl").read_text().splitlines()]
    said = [m["content"] for m in log if m["role"] == "assistant"]
    assert "The test fails on the original, so the design is wrong; fixing it." in said
    assert sum(m["role"] == "tool" for m in log) == 4
    assert (d / "history" / "001" / "test_spec.py").exists()
    no_secret_in(d)


def test_agent_budget_exhausted(tmp_path, _clean_sandboxes):
    api = FakeAPI(tool("read_file", "Read the spec again.", path="spec.md"))
    info = agent(tmp_path, api, ["--max-calls", "2"])
    assert info["stop_reason"] == "budget_exhausted" and info["state"] == "budget_exhausted"
    assert info["turns"] == 3 and not (tmp_path / "a" / "submission").exists()


def test_agent_bad_calls_then_nudged_then_stops(tmp_path, _clean_sandboxes):
    bad = {"content": "trying", "tool_calls": [
        {"id": "a", "type": "function", "function": {"name": "read_file", "arguments": "{not json"}},
        {"id": "b", "type": "function", "function": {"name": "rm_rf", "arguments": "{}"}}]}
    seen = []

    def chat(body):
        seen.append(body["messages"][-1])
        return {"content": "I think the bug is on line 12."}

    api = FakeAPI(bad, chat)
    info = agent(tmp_path, api)
    assert info["stop_reason"] == "no_tool_calls" and info["state"] == "no_submission"
    assert info["turns"] == 3   # bad calls, text, nudged text
    tool_msgs = [m for m in api.bodies[1]["messages"] if m["role"] == "tool"]
    texts = [m["content"] if isinstance(m["content"], str) else m["content"][0]["text"] for m in tool_msgs]
    assert "not a valid JSON object" in texts[0] and "no tool 'rm_rf'" in texts[1]
    assert seen[1]["content"][0]["text"] == ra.NUDGE
    trace = (tmp_path / "a" / "trace.jsonl")
    assert not trace.exists() or trace.read_text() == ""   # nothing reached the server


def test_agent_api_error_recorded(tmp_path, _clean_sandboxes):
    api = FakeAPI((500, b'{"error": {"message": "upstream down"}}'))
    info = agent(tmp_path, api)
    assert info["stop_reason"] == "api_error" and info["status"] == "error" and "upstream down" in info["error"]
    assert info["state"] == "no_submission" and len(api.bodies) == 2
    assert json.loads((tmp_path / "a" / "llm.json").read_text())["status"] == "error"


def test_agent_token_cap(tmp_path, _clean_sandboxes):
    api = FakeAPI(tool("read_file", "look", path="spec.md"), usage={"prompt_tokens": 600, "completion_tokens": 0})
    info = agent(tmp_path, api, cfg={**CFG, "max_run_tokens": 1000})
    assert info["stop_reason"] == "token_cap" and info["turns"] == 2


def test_agent_turn_cap(tmp_path, _clean_sandboxes):
    api = FakeAPI(tool("read_file", "look", path="spec.md"))
    info = agent(tmp_path, api, cfg={**CFG, "max_turns": 3})
    assert info["stop_reason"] == "turn_cap" and info["turns"] == 3 and info["state"] == "no_submission"


def test_env_file(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# comment\nOPENROUTER_API_KEY='sk-from-file'\nexport PRIP_TEST_A=\"x y\"\nPRIP_TEST_EMPTY=\nnot a line\n")
    monkeypatch.delenv(KEY_VAR)
    monkeypatch.delenv("PRIP_TEST_A", raising=False)
    monkeypatch.setenv("PRIP_TEST_KEEP", "env")
    f.write_text(f.read_text() + "PRIP_TEST_KEEP=file\n")
    llm_mod.load_env_file(f)
    import os
    assert os.environ[KEY_VAR] == "sk-from-file" and os.environ["PRIP_TEST_A"] == "x y"
    assert "PRIP_TEST_EMPTY" not in os.environ and os.environ["PRIP_TEST_KEEP"] == "env"
    monkeypatch.delenv("PRIP_TEST_A")
    llm_mod.load_env_file(tmp_path / "missing")   # no file: nothing happens
