"""Phase 5 end-to-end check: a scripted client stands in for the agent, over real MCP stdio.

For every dev bug (bugs/dev_set.json) it starts the tool server (one process + one sandbox per
run) and does two runs:
  fix        reads the original, writes the hidden reference test as its own test, runs it on the
             original (must fail where the manifest says the reference test detects the bug),
             writes golden.v as the fix, lints it (clean), reruns the test (must pass), submits
             with an exact line
  unchanged  submits the buggy file as is, with an exact line
Then grades every run in the container: fix -> PASS + exact, unchanged -> FAIL + exact.

The client is trusted test code, so it may read golden.v and ref_test.py; an agent never sees them.
Runs on the host (see `make tools-check`).
"""

import asyncio
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from toolserver.sandbox import IMAGE, remove_leftovers  # noqa: E402
from toolserver.server import load_bug  # noqa: E402

OUT = ROOT / "build" / "tools_check"
RUNS = OUT / "runs"
DOCKER = ["docker", "run", "--rm", "-v", f"{ROOT}:/work", "-w", "/work", IMAGE]
PARALLEL = 4


async def call(c, problems, name, args, expect=None):
    """One tool call; `expect` is a regex the result must contain."""
    r = await c.call_tool(name, args)
    text = r.content[0].text if r.content else ""
    if r.is_error:
        problems.append(f"{name} errored: {text[:300]}")
    elif expect and not re.search(expect, text):
        problems.append(f"{name}: expected /{expect}/, got: {text[:300]}")
    return text


async def one_run(bug: dict, kind: str, line: int, sem) -> list[str]:
    run_id = f"{bug['id']}-{kind}"
    problems = []
    async with sem:
        params = StdioServerParameters(command=sys.executable, cwd=str(ROOT), args=[
            "-m", "toolserver.server", "--bug", bug["id"], "--runs-dir", str(RUNS), "--run-id", run_id])
        async with Client(params) as c:
            top = bug["top"]
            if kind == "fix":
                design = ROOT / "designs" / bug["design"]
                await call(c, problems, "read_file", {"path": f"original/{top}.v"})
                await call(c, problems, "write_file", {"path": "tests/test_ref.py",
                                                       "content": (design / "ref_test.py").read_text()})
                want = r"\d+ passed, [1-9]\d* failed" if bug["reference_test_detected"] else r"\d+ passed, 0 failed"
                await call(c, problems, "run_cocotb", {"test_file": "tests/test_ref.py", "target": "original"},
                           want)
                await call(c, problems, "write_file", {"path": f"{top}.v",
                                                       "content": (design / "golden.v").read_text()})
                await call(c, problems, "lint", {}, r"^lint: clean")
                await call(c, problems, "run_cocotb", {"test_file": "tests/test_ref.py"}, r"[1-9]\d* passed, 0 failed")
            await call(c, problems, "submit_patch", {"line": line, "explanation": f"scripted {kind}"},
                       r"^Submission received\. The run is over\.$")
    expect = {"repair": "PASS" if kind == "fix" else "FAIL", "exact": True}
    (RUNS / run_id / "check_expect.json").write_text(json.dumps(expect) + "\n")
    return [f"{run_id}: {p}" for p in problems]


async def drive(bugs, lines):
    sem = asyncio.Semaphore(PARALLEL)
    jobs = [one_run(b, kind, lines[b["id"]], sem) for b in bugs for kind in ("fix", "unchanged")]
    return [p for ps in await asyncio.gather(*jobs) for p in ps]


def main():
    remove_leftovers()
    shutil.rmtree(OUT, ignore_errors=True)
    RUNS.mkdir(parents=True)
    ids = [b["id"] for b in json.loads((ROOT / "bugs" / "dev_set.json").read_text())["bugs"]]
    bugs = [load_bug(i) for i in ids]
    p = subprocess.run(DOCKER + ["python", "tools/grade_runs.py", "lines", *ids], capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"could not compute expected lines:\n{p.stderr}")
    lines = json.loads(p.stdout)

    print(f"driving {2 * len(bugs)} runs over MCP ({PARALLEL} at a time)...", flush=True)
    problems = asyncio.run(drive(bugs, lines))
    leftover = subprocess.run(["docker", "ps", "-q", "--filter", "label=prip.sandbox"],
                              capture_output=True, text=True).stdout.split()
    if leftover:
        problems.append(f"{len(leftover)} sandbox containers still running after the runs ended")
    for p in problems:
        print("PROBLEM", p)

    print("grading in the container...", flush=True)
    g = subprocess.run(DOCKER + ["python", "tools/grade_runs.py", "grade", "build/tools_check/runs", "--check"])
    ok = not problems and g.returncode == 0
    print(f"\ntools-check: {len(problems)} client problems; grading {'OK' if g.returncode == 0 else 'MISMATCHES'}"
          f" -> {'PASSED' if ok else 'FAILED'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
