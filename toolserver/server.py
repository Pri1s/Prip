"""MCP tool server for one agent run on one benchmark bug.

Runs on the host, outside the sandbox: it holds the state the agent must not be able to touch
(the one submission, the call and time budget, the trace). Tools that run agent-controlled code
(lint, run_cocotb) execute in the run's sandbox container; read_file / write_file are plain file
operations on the workspace, restricted to its fixed layout.

Tools:
  read_file(path, start_line?, end_line?)   numbered lines
  write_file(path, content)                 <top>.v or tests/<name>.py
  lint()                                    iverilog -g2005 + yosys elaboration + patch source rules
  run_cocotb(test_file, target?, testcase?) one of the agent's tests, on the working copy or original
  submit_patch(line, explanation)           submits <top>.v + the claimed line; once; ends the run

Every call is logged to <run>/trace.jsonl; every run_cocotb also saves a copy of the test files
it ran (<run>/history/<n>/) so Phase 6 can replay them on golden RTL to measure detection.

Usage (host venv; one process per run, speaking MCP over stdio):
  .venv/bin/python -m toolserver.server --bug token_bucket_07 --runs-dir runs
"""

import argparse
import hashlib
import json
import secrets
import sys
import time
from pathlib import Path

from grader.equiv import FORMAL_CELLS, check_patch_text
from toolserver import workspace as ws_mod
from toolserver.sandbox import IMAGE, Sandbox
from toolserver.workspace import WorkspaceError

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "bugs" / "manifest.jsonl"
MAX_CALLS = 40
MAX_SECONDS = 15 * 60
TOOL_TIMEOUT = 60       # seconds per lint / run_cocotb call, like the reference test's limit
OUTPUT_LIMIT = 8000     # characters of log text returned per call (the end is kept)
MAX_EXPLANATION = 4000

INSTRUCTIONS = """\
You are debugging one Verilog design that has a bug. Your workspace:
  {rtl}            the buggy RTL; edit this file to fix the bug (it is what you submit)
  spec.md          what the design is supposed to do
  {original}   the buggy file as given (read-only); use its line numbers when you submit
  tests/           write your own cocotb tests here as tests/<name>.py
No testbench is provided. Tests run with cocotb 2.0 and Icarus Verilog (timescale 1ns/1ps) on
{rtl} (target "working") or {original} (target "original"); there is no network.
Finish with exactly one submit_patch(line, explanation): `line` is the buggy line's number in
{original}. Budget: {calls} tool calls and {minutes} minutes."""


def load_bug(bug_id: str) -> dict:
    for line in MANIFEST.read_text().splitlines():
        if line.strip() and (bug := json.loads(line))["id"] == bug_id:
            return bug
    raise KeyError(f"no bug {bug_id!r} in {MANIFEST}")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _tail(text: str, limit: int = OUTPUT_LIMIT) -> str:
    text = text.strip()
    return text if len(text) <= limit else f"[... {len(text) - limit} earlier characters cut]\n" + text[-limit:]


def _box_result(out: str) -> dict | None:
    lines = [l for l in out.splitlines() if l.startswith("BOX_RESULT ")]
    try:
        return json.loads(lines[-1][len("BOX_RESULT "):]) if lines else None
    except json.JSONDecodeError:
        return None


class ToolFailure(Exception):
    """A tool call that failed in a way the agent should read (bad path, run over, ...)."""


class Run:
    """All tool behavior for one run, independent of the MCP transport (tests call it directly)."""

    def __init__(self, bug: dict, run_dir: Path, sandbox=None, max_calls=MAX_CALLS,
                 max_seconds=MAX_SECONDS, tool_timeout=TOOL_TIMEOUT, seed=None, image=IMAGE):
        self.bug = bug
        self.dir = Path(run_dir)
        self.ws = ws_mod.create(bug, self.dir / "workspace")
        self.sandbox = sandbox or Sandbox(self.ws.root, image=image)
        self.max_calls, self.max_seconds, self.tool_timeout = max_calls, max_seconds, tool_timeout
        self.seed = seed if seed is not None else secrets.randbelow(2**31)
        self.calls = 0
        self.cocotb_runs = 0
        self.started = time.time()
        self.state = "running"   # -> submitted | budget_exhausted | no_submission
        self.n_lines = len(self.ws.read(self.ws.original).splitlines())
        self._write_run_json()

    # -- bookkeeping ---------------------------------------------------------------------------

    def _write_run_json(self):
        info = {"bug": self.bug["id"], "top": self.ws.top, "seed": self.seed, "state": self.state,
                "started": self.started, "calls": self.calls, "max_calls": self.max_calls,
                "max_seconds": self.max_seconds, "elapsed_s": round(time.time() - self.started, 1)}
        (self.dir / "run.json").write_text(json.dumps(info, indent=2) + "\n")

    def _trace(self, entry: dict):
        with open(self.dir / "trace.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")

    def instructions(self) -> str:
        return INSTRUCTIONS.format(rtl=self.ws.rtl, original=self.ws.original, calls=self.max_calls,
                                   minutes=self.max_seconds // 60)

    def _budget_note(self) -> str:
        left = max(0, int(self.max_seconds - (time.time() - self.started)))
        return f"\n(budget left: {self.max_calls - self.calls} calls, {left} s)"

    def call(self, tool: str, **args) -> str:
        """Runs one tool call with budget checks and tracing. Raises ToolFailure on refusal."""
        t0 = time.time()
        logged = {k: ({"sha256": _sha(v), "chars": len(v)} if k in ("content", "explanation") else v)
                  for k, v in args.items()}
        entry = {"n": self.calls + 1, "t": round(t0 - self.started, 2), "tool": tool, "args": logged}
        try:
            if self.state != "running":
                raise ToolFailure(f"the run is over ({self.state}); no more tool calls are accepted")
            self.calls += 1
            if self.calls > self.max_calls or t0 - self.started > self.max_seconds:
                self.state = "budget_exhausted"
                raise ToolFailure("budget exhausted: the run ended without a submission")
            text, detail = getattr(self, f"_{tool}")(**args)
            entry.update(ok=True, result=detail)
            return text if self.state != "running" else text + self._budget_note()
        except (ToolFailure, WorkspaceError) as e:
            entry.update(ok=False, error=str(e))
            raise ToolFailure(str(e) + (self._budget_note() if self.state == "running" else ""))
        finally:
            entry["duration_s"] = round(time.time() - t0, 2)
            self._trace(entry)
            self._write_run_json()

    def finish(self):
        if self.state == "running":
            self.state = "no_submission"
        self.sandbox.stop()
        self._write_run_json()

    # -- tools ---------------------------------------------------------------------------------

    def _read_file(self, path: str, start_line: int | None = None, end_line: int | None = None):
        lines = self.ws.read(path).splitlines()
        lo = max(1, start_line or 1)
        hi = min(len(lines), end_line or len(lines))
        if lo > hi and lines:
            raise ToolFailure(f"{path} has {len(lines)} lines; asked for {lo}-{hi}")
        width = len(str(hi))
        body = "\n".join(f"{i:>{width}}| {lines[i - 1]}" for i in range(lo, hi + 1))
        if len(body) > OUTPUT_LIMIT:
            body = body[:OUTPUT_LIMIT] + "\n[... cut; ask for a smaller start_line/end_line range]"
        return f"{path} (lines {lo}-{hi} of {len(lines)})\n{body}", {"lines": [lo, hi]}

    def _write_file(self, path: str, content: str):
        self.ws.write(path, content)
        return f"wrote {path} ({len(content.splitlines())} lines)", {"sha256": _sha(content)}

    def _lint(self):
        rtl = self.ws.read(self.ws.rtl)
        rule = check_patch_text(rtl)
        rc, out, killed = self.sandbox.exec(
            ["python", "/opt/box/box_runner.py", "lint", "--rtl", f"/ws/{self.ws.rtl}",
             "--top", self.ws.top, "--forbid", ",".join(sorted(FORMAL_CELLS))], self.tool_timeout)
        res = _box_result(out)
        if killed or res is None:
            raise ToolFailure("lint did not finish" + (" (time limit)" if killed else "") + "\n" + _tail(out))
        problems = res["problems"] + ([f"not allowed in a submission: {rule}"] if rule else [])
        head = "lint: clean" if not problems else "lint: PROBLEMS\n" + "\n".join(f"- {p}" for p in problems)
        log = _tail(res["log"])
        return head + (f"\n\n{log}" if log else ""), {"ok": not problems, "problems": problems}

    def _run_cocotb(self, test_file: str, target: str = "working", testcase: str | None = None):
        if target not in ("working", "original"):
            raise ToolFailure('target must be "working" or "original"')
        name = test_file.removeprefix("tests/")
        if not ws_mod.TEST_NAME.fullmatch(name):
            raise ToolFailure(f"test_file must name a file in tests/, like tests/test_basic.py")
        if testcase is not None and not testcase.isidentifier():
            raise ToolFailure("testcase must be a test function name")
        self.ws.read(f"tests/{name}")   # exists and is a regular file
        self.cocotb_runs += 1
        n = self.cocotb_runs
        hist = self.dir / "history" / f"{n:03d}"
        files = self.ws.snapshot_tests(hist)
        rtl = self.ws.rtl if target == "working" else self.ws.original
        (hist / "_rtl.v").write_text(self.ws.read(rtl))
        rc, out, killed = self.sandbox.exec(
            ["python", "/opt/box/box_runner.py", "cocotb", "--rtl", f"/ws/{rtl}", "--top", self.ws.top,
             "--module", name.removesuffix(".py"), "--seed", str(self.seed), "--build", f"/tmp/build_{n}"]
            + (["--testcase", testcase] if testcase else []), self.tool_timeout)
        res = _box_result(out) if not killed else None
        log = "\n".join(l for l in out.splitlines() if not l.startswith("BOX_RESULT "))
        if killed:
            status, tests = "timeout", []
        elif res is None:
            status, tests = "crash", []
        else:
            status, tests = res["status"], res["tests"]
        detail = {"history": f"history/{n:03d}", "files": files, "target": target,
                  "rtl_sha256": _sha((hist / "_rtl.v").read_text()), "seed": self.seed, "status": status, "tests": tests}
        (hist / "_result.json").write_text(json.dumps(detail, indent=2) + "\n")

        head = f"run_cocotb tests/{name} on {rtl} (target {target}, seed {self.seed})"
        if status == "timeout":
            summary = (f"TIMEOUT: killed after {self.tool_timeout} s (the simulation never finished: "
                       f"an endless test or a combinational loop that never settles)")
        elif status == "build_failed":
            summary = "BUILD FAILED: the RTL did not compile\n" + (res.get("error") or "")
        elif status in ("crash", "no_tests"):
            summary = ("CRASH: no test results (simulator or test module crashed)" if status == "crash"
                       else "NO TESTS: no @cocotb.test() functions ran")
        else:
            passed = sum(t["passed"] for t in tests)
            summary = f"{passed} passed, {len(tests) - passed} failed\n" + "\n".join(
                f"{'PASS' if t['passed'] else 'SKIP' if t['skipped'] else 'FAIL'} {t['name']}"
                + (f" (at {t['sim_time_ns']} ns)" if not t["passed"] and t.get("sim_time_ns") else "")
                + (f": {t['message']}" if t["message"] else "") for t in tests)
        return f"{head}\n{summary}\n\n--- log (end) ---\n{_tail(log)}", detail

    def _submit_patch(self, line: int, explanation: str = ""):
        if isinstance(line, bool) or not isinstance(line, int) or not 1 <= line <= self.n_lines:
            raise ToolFailure(f"line must be a line number of {self.ws.original} (1-{self.n_lines}); "
                              f"nothing was submitted")
        if len(explanation) > MAX_EXPLANATION:
            raise ToolFailure(f"explanation is longer than {MAX_EXPLANATION} characters; nothing was submitted")
        sub = self.dir / "submission"
        sub.mkdir()
        patch = self.ws.read(self.ws.rtl)
        (sub / self.ws.rtl).write_text(patch)
        tests = self.ws.snapshot_tests(sub / "tests")
        info = {"bug": self.bug["id"], "file": self.ws.rtl, "line": line, "explanation": explanation,
                "patch_sha256": _sha(patch), "tests": tests, "submitted_t": round(time.time() - self.started, 2)}
        (sub / "submission.json").write_text(json.dumps(info, indent=2) + "\n")
        self.state = "submitted"
        return "Submission received. The run is over.", {"line": line, "patch_sha256": info["patch_sha256"]}


def build_server(run: Run):
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError

    server = MCPServer("rtl-debug-tools", instructions=run.instructions())

    def call(tool, **args):
        try:
            return run.call(tool, **args)
        except ToolFailure as e:
            raise ToolError(str(e))

    @server.tool()
    def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> str:
        """Read a workspace file with line numbers. Paths: the RTL file, spec.md, original/<file>.v,
        tests/<name>.py. Optionally limit to start_line..end_line (1-based, inclusive)."""
        return call("read_file", path=path, start_line=start_line, end_line=end_line)

    @server.tool()
    def write_file(path: str, content: str) -> str:
        """Replace the whole content of the RTL file or of a test file tests/<name>.py."""
        return call("write_file", path=path, content=content)

    @server.tool()
    def lint() -> str:
        """Compile the working RTL file with iverilog -g2005 and elaborate it with yosys. Also
        reports constructs a submission may not use (`include, `ifdef, file I/O tasks, formal-only
        constructs)."""
        return call("lint")

    @server.tool()
    def run_cocotb(test_file: str, target: str = "working", testcase: str | None = None) -> str:
        """Run one of your cocotb test files (tests/<name>.py) against the working RTL file
        (target "working") or the original buggy file (target "original"). Optionally run only
        one test function. Each run is limited to 60 seconds."""
        return call("run_cocotb", test_file=test_file, target=target, testcase=testcase)

    @server.tool()
    def submit_patch(line: int, explanation: str = "") -> str:
        """Submit the current working RTL file as your fix, with the number of the buggy line as
        numbered in original/<file>.v. You can submit only once; the run ends after it."""
        return call("submit_patch", line=line, explanation=explanation)

    return server


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--bug", required=True, help="bug ID from bugs/manifest.jsonl")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--run-id", help="default: <bug>-<time>-<random>")
    ap.add_argument("--max-calls", type=int, default=MAX_CALLS)
    ap.add_argument("--max-seconds", type=int, default=MAX_SECONDS)
    ap.add_argument("--tool-timeout", type=int, default=TOOL_TIMEOUT)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--image", default=IMAGE)
    a = ap.parse_args()
    bug = load_bug(a.bug)
    run_id = a.run_id or f"{bug['id']}-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    run = Run(bug, Path(a.runs_dir) / run_id, max_calls=a.max_calls, max_seconds=a.max_seconds,
              tool_timeout=a.tool_timeout, seed=a.seed, image=a.image)
    print(f"run {run_id}: {run.dir}", file=sys.stderr)
    try:
        run.sandbox.start()
        build_server(run).run()
    finally:
        run.finish()


if __name__ == "__main__":
    main()
