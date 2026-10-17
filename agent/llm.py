"""OpenRouter chat-completions client: the one place that holds the API key, retries and records cost.

Host only. The key comes from OPENROUTER_API_KEY (the environment, or the repo's gitignored .env)
and is sent in the Authorization header and nowhere else: it is never written to a run directory or passed to the tool server or sandbox.

Uses the OpenAI-compatible endpoint, so tool calls are OpenAI-style function calls. For Anthropic
models the system prompt and the newest message get a cache breakpoint, so each turn re-reads the
growing conversation from the prompt cache instead of paying full input price for it again.
"""

import asyncio
import copy
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://openrouter.ai/api/v1/chat/completions"
KEY_VAR = "OPENROUTER_API_KEY"
CONFIG = Path(__file__).resolve().parent / "config.json"
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"   # gitignored; see .env.example
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
RETRY_WAIT_S = 10


class LLMError(Exception):
    """The call failed even after the retry (or can't be retried); the run records it as an error."""


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(Path(path).read_text())


def load_env_file(path: Path = ENV_FILE):
    """Sets KEY=VALUE lines from the repo's .env into the environment (variables already set win).
    Called by the command-line entry points only."""
    path = Path(path)
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key and value and key not in os.environ:
            os.environ[key] = value


def http_post(url: str, body: bytes, headers: dict, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _with_breakpoint(msg: dict) -> dict:
    msg = dict(msg)
    if isinstance(msg.get("content"), str) and msg["content"]:
        msg["content"] = [{"type": "text", "text": msg["content"], "cache_control": {"type": "ephemeral"}}]
    return msg


class Usage:
    """Token and cost totals for one run."""

    def __init__(self):
        self.calls = self.prompt = self.completion = self.cached = 0
        self.cost = 0.0

    def add(self, u: dict):
        self.calls += 1
        self.prompt += u.get("prompt_tokens") or 0
        self.completion += u.get("completion_tokens") or 0
        self.cached += (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        self.cost += u.get("cost") or 0.0

    @property
    def total(self) -> int:
        return self.prompt + self.completion

    def as_dict(self) -> dict:
        return {"llm_calls": self.calls, "prompt_tokens": self.prompt, "completion_tokens": self.completion,
                "cached_tokens": self.cached, "cost_usd": round(self.cost, 6)}


class OpenRouter:
    def __init__(self, model: str, temperature: float, max_tokens: int, cache: bool = True,
                 post=http_post, timeout: float = 300, wait_s: float = RETRY_WAIT_S):
        self.key = os.environ.get(KEY_VAR)
        if not self.key:
            raise LLMError(f"set {KEY_VAR} in the environment")
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens
        self.cache = cache and model.startswith("anthropic/")
        self.post, self.timeout, self.wait_s = post, timeout, wait_s
        self.usage = Usage()

    def body(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        msgs = copy.deepcopy(messages)
        if self.cache:
            if msgs and msgs[0]["role"] == "system":
                msgs[0] = _with_breakpoint(msgs[0])
            if len(msgs) > 1:
                msgs[-1] = _with_breakpoint(msgs[-1])
        body = {"model": self.model, "messages": msgs, "temperature": self.temperature,
                "max_tokens": self.max_tokens, "usage": {"include": True}}
        if tools:
            body["tools"] = tools
        return body

    def _once(self, payload: bytes) -> tuple[dict | None, str, bool]:
        """One HTTP call. Returns (response, error text, retryable)."""
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
                   "X-Title": "rtl-debug-agent"}
        try:
            status, raw = self.post(URL, payload, headers, self.timeout)
        except (OSError, TimeoutError) as e:
            return None, f"network error: {type(e).__name__}: {e}", True
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None, f"HTTP {status}: response is not JSON: {raw[:300]!r}", status in RETRY_STATUS or status == 200
        if status != 200 or "error" in data or not data.get("choices"):
            err = (data.get("error") or {}) if isinstance(data, dict) else {}
            return None, f"HTTP {status}: {err.get('message') or str(data)[:300]}", status in RETRY_STATUS or status == 200
        return data, "", False

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """One completion: {"message", "finish_reason", "usage"}. Retries once on a transient failure."""
        payload = json.dumps(self.body(messages, tools)).encode()
        data, err, retry = await asyncio.to_thread(self._once, payload)
        if data is None and retry:
            await asyncio.sleep(self.wait_s)
            data, err, retry = await asyncio.to_thread(self._once, payload)
        if data is None:
            raise LLMError(err)
        usage = data.get("usage") or {}
        self.usage.add(usage)
        choice = data["choices"][0]
        return {"message": choice.get("message") or {}, "finish_reason": choice.get("finish_reason"),
                "usage": usage}
