"""Tests for the Phase 5 tool server, run on the host against a real sandbox (`make tools-test`).

Most tests try to break out: read or write outside the workspace, plant a symlink, reach the
network, find the answer key, outlive a call, flood the output, submit twice, overspend the budget.
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest

from toolserver.sandbox import remove_leftovers
from toolserver.server import OUTPUT_LIMIT, Run, ToolFailure, load_bug

ROOT = Path(__file__).resolve().parent.parent
BUG = "token_bucket_07"
GOLDEN = ROOT / "designs" / "token_bucket" / "golden.v"


@pytest.fixture(scope="session", autouse=True)
def _clean_sandboxes():
    remove_leftovers()
    yield
    remove_leftovers()


@pytest.fixture
def run(tmp_path):
    r = Run(load_bug(BUG), tmp_path / "run", tool_timeout=20, seed=1)
    r.sandbox.start()
    yield r
    r.finish()


def refused(r, tool, **args) -> str:
    with pytest.raises(ToolFailure) as e:
        r.call(tool, **args)
    return str(e.value)


def test_workspace_has_only_agent_files(run):
    files = sorted(str(p.relative_to(run.ws.root)) for p in run.ws.root.rglob("*") if p.is_file())
    assert files == ["original/token_bucket.v", "spec.md", "token_bucket.v"]
    assert (run.ws.root / "token_bucket.v").read_text() == (ROOT / "bugs/token_bucket/token_bucket_07.v").read_text()
    assert oct((run.ws.root / "original/token_bucket.v").stat().st_mode & 0o777) == "0o444"
    assert BUG not in run.instructions()


@pytest.mark.parametrize("path", ["../../designs/token_bucket/golden.v", str(GOLDEN), "/etc/passwd",
                                  "original/../token_bucket.v", "tests/../token_bucket.v", "tests/a/b.py",
                                  "./token_bucket.v", "tests\\x.py", "run.json", "trace.jsonl", ""])
def test_paths_outside_layout_refused(run, path):
    refused(run, "read_file", path=path)
    refused(run, "write_file", path=path, content="x")


def test_original_and_spec_not_writable(run):
    for path in ["original/token_bucket.v", "spec.md", "tests/notes.txt", "helper.v"]:
        refused(run, "write_file", path=path, content="x")
    assert (run.ws.root / "original/token_bucket.v").read_text() == run.ws.read("token_bucket.v")


def test_host_never_follows_symlinks(run, tmp_path):
    # The sandbox can't create these (read-only mount); this checks the host's own line of defense.
    before = GOLDEN.read_text()
    os.symlink(GOLDEN, run.ws.root / "tests" / "leak.py")
    assert "is not a regular file" in refused(run, "read_file", path="tests/leak.py")
    assert "is not a regular file" in refused(run, "write_file", path="tests/leak.py", content="pwned")
    os.mkfifo(run.ws.root / "tests" / "fifo.py")
    refused(run, "read_file", path="tests/fifo.py")          # must not hang
    assert run.ws.test_files() == []                         # neither counts as a test file

    os.rename(run.ws.root / "tests", tmp_path / "real_tests")
    os.symlink(GOLDEN.parent, run.ws.root / "tests")
    assert "not a plain directory" in refused(run, "write_file", path="tests/golden.py", content="x")
    assert not (GOLDEN.parent / "golden.py").exists()
    assert GOLDEN.read_text() == before


ESCAPE_TEST = r'''
import os, socket, subprocess
import cocotb

@cocotb.test()
async def no_network(dut):
    for target in [("1.1.1.1", 53), ("example.com", 80)]:
        try:
            socket.create_connection(target, timeout=3).close()
        except OSError:
            continue
        raise AssertionError(f"connected to {target}")

@cocotb.test()
async def workspace_read_only(dut):
    for path in ["/ws/token_bucket.v", "/ws/original/token_bucket.v", "/ws/tests/new.py", "/ws/x"]:
        try:
            open(path, "a").close()
        except OSError:
            continue
        raise AssertionError(f"wrote {path}")
    for link in ["/ws/tests/leak.py", "/ws/leak"]:
        try:
            os.symlink("/etc/passwd", link)
        except OSError:
            continue
        raise AssertionError(f"created {link}")

@cocotb.test()
async def root_fs_read_only_and_unprivileged(dut):
    assert os.getuid() != 0 and os.getgid() != 0
    for path in ["/opt/x", "/etc/x", "/usr/bin/x"]:
        try:
            open(path, "w").close()
        except OSError:
            continue
        raise AssertionError(f"wrote {path}")

@cocotb.test()
async def no_answer_key_anywhere(dut):
    found = []
    for top in ["/"]:
        for d, dirs, files in os.walk(top):
            if d in ("/proc", "/sys", "/dev"):
                dirs[:] = []
                continue
            found += [os.path.join(d, f) for f in files
                      if f in ("golden.v", "ref_test.py", "manifest.jsonl", "meta.json", "eval_set.json")
                      or f.startswith("token_bucket_")]
    assert found == [], found
    assert not os.path.exists("/work") or os.listdir("/work") == []
'''


def test_sandbox_contains_agent_code(run):
    run.call("write_file", path="tests/test_escape.py", content=ESCAPE_TEST)
    out = run.call("run_cocotb", test_file="tests/test_escape.py")
    assert "4 passed, 0 failed" in out, out


HANG_TEST = r'''
import subprocess
import cocotb

@cocotb.test()
async def leave_a_background_process_and_hang(dut):
    subprocess.Popen(["sleep", "1001"], start_new_session=True)
    while True:
        pass
'''

CHECK_TEST = r'''
import os
import cocotb

@cocotb.test()
async def nothing_left_running(dut):
    left = []
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode()
            except OSError:
                continue
            if "sleep 1001" in cmd or "test_hang" in cmd:
                left.append(cmd)
    assert left == [], left
'''


def test_hung_test_killed_and_nothing_survives(run):
    run.call("write_file", path="tests/test_hang.py", content=HANG_TEST)
    t = time.time()
    out = run.call("run_cocotb", test_file="tests/test_hang.py")
    assert "TIMEOUT" in out and time.time() - t < 45
    run.call("write_file", path="tests/test_check.py", content=CHECK_TEST)
    out = run.call("run_cocotb", test_file="tests/test_check.py")
    assert "1 passed" in out, out


def test_rtl_that_never_advances_time_times_out(run):
    rtl = run.ws.read("token_bucket.v").replace("endmodule", "reg osc = 1'b0;\ninitial forever osc = ~osc;\nendmodule")
    run.call("write_file", path="token_bucket.v", content=rtl)
    run.call("write_file", path="tests/test_ref.py", content=(GOLDEN.parent / "ref_test.py").read_text())
    assert "TIMEOUT" in run.call("run_cocotb", test_file="tests/test_ref.py")


def test_output_flood_is_cut(run):
    run.call("write_file", path="tests/test_flood.py",
             content="import cocotb\n@cocotb.test()\nasync def flood(dut):\n    print('x' * 3_000_000)\n")
    out = run.call("run_cocotb", test_file="tests/test_flood.py")
    assert len(out) < OUTPUT_LIMIT + 1500 and "earlier characters cut" in out


def test_detects_on_original_and_passes_fix_with_history(run):
    run.call("write_file", path="tests/test_ref.py", content=(GOLDEN.parent / "ref_test.py").read_text())
    assert "0 passed, 1 failed" in run.call("run_cocotb", test_file="tests/test_ref.py", target="original")
    run.call("write_file", path="token_bucket.v", content=GOLDEN.read_text())
    assert "lint: clean" in run.call("lint")
    assert "1 passed, 0 failed" in run.call("run_cocotb", test_file="test_ref.py")
    h1 = json.loads((run.dir / "history/001/_result.json").read_text())
    h2 = json.loads((run.dir / "history/002/_result.json").read_text())
    assert (h1["target"], h1["tests"][0]["passed"], h2["target"], h2["tests"][0]["passed"]) == \
        ("original", False, "working", True)
    assert (run.dir / "history/001/_rtl.v").read_text() == run.ws.read("original/token_bucket.v")
    assert (run.dir / "history/002/_rtl.v").read_text() == GOLDEN.read_text()
    assert h1["seed"] == h2["seed"] == 1


def test_lint_reports_problems(run):
    rtl = run.ws.read("token_bucket.v")
    run.call("write_file", path="token_bucket.v", content=rtl.replace("endmodule", "integer f;\ninitial f = $fopen(\"/ws/spec.md\");\nendmodule"))
    assert "$fopen" in run.call("lint")
    run.call("write_file", path="token_bucket.v", content=rtl.replace("endmodule", "always @(posedge clk) assume(rst);\nendmodule"))
    assert "formal-only" in run.call("lint")
    run.call("write_file", path="token_bucket.v", content=rtl.replace(";", "", 1))
    assert "iverilog -g2005 failed" in run.call("lint")


def test_submit_once(run):
    assert "1-31" in refused(run, "submit_patch", line=0, explanation="")
    run.call("write_file", path="token_bucket.v", content=GOLDEN.read_text())
    assert run.call("submit_patch", line=24, explanation="fix") == "Submission received. The run is over."
    sub = json.loads((run.dir / "submission/submission.json").read_text())
    assert sub["line"] == 24 and (run.dir / "submission/token_bucket.v").read_text() == GOLDEN.read_text()
    for tool, args in [("submit_patch", {"line": 24}), ("lint", {}), ("read_file", {"path": "spec.md"})]:
        assert "run is over (submitted)" in refused(run, tool, **args)
    trace = [json.loads(l) for l in (run.dir / "trace.jsonl").read_text().splitlines()]
    assert [t["tool"] for t in trace][:3] == ["submit_patch", "write_file", "submit_patch"]
    assert "content" in trace[1]["args"] and "sha256" in trace[1]["args"]["content"]


def test_call_budget(tmp_path):
    r = Run(load_bug(BUG), tmp_path / "run", max_calls=2, seed=1)
    try:
        r.call("read_file", path="spec.md")
        r.call("read_file", path="spec.md")
        assert "budget exhausted" in refused(r, "read_file", path="spec.md")
        assert "run is over (budget_exhausted)" in refused(r, "submit_patch", line=1)
    finally:
        r.finish()
    assert json.loads((r.dir / "run.json").read_text())["state"] == "budget_exhausted"
    assert not (r.dir / "submission").exists()


def test_time_budget(tmp_path):
    r = Run(load_bug(BUG), tmp_path / "run", max_seconds=0, seed=1)
    time.sleep(0.01)
    try:
        assert "budget exhausted" in refused(r, "read_file", path="spec.md")
    finally:
        r.finish()


def test_over_mcp_stdio(tmp_path):
    from mcp import Client, StdioServerParameters

    async def session():
        params = StdioServerParameters(command=sys.executable, cwd=str(ROOT), args=[
            "-m", "toolserver.server", "--bug", BUG, "--runs-dir", str(tmp_path), "--run-id", "r1"])
        async with Client(params) as c:
            tools = sorted(t.name for t in (await c.list_tools()).tools)
            assert tools == ["lint", "read_file", "run_cocotb", "submit_patch", "write_file"]
            assert "original/token_bucket.v" in c.instructions
            r = await c.call_tool("read_file", {"path": "../../designs/token_bucket/golden.v"})
            assert r.is_error
            r = await c.call_tool("read_file", {"path": "original/token_bucket.v", "start_line": 24, "end_line": 24})
            assert not r.is_error and r.content[0].text.splitlines()[1].startswith("24| ")
            r = await c.call_tool("submit_patch", {"line": 24, "explanation": "no change"})
            assert r.content[0].text == "Submission received. The run is over."

    asyncio.run(session())
    assert json.loads((tmp_path / "r1/run.json").read_text())["state"] == "submitted"
