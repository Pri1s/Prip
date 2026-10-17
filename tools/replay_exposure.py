"""Phase 6b exposure: replays each run's own tests on the buggy RTL and on the golden RTL.

Host only (it starts sandboxes, like the tool server). For every run in the given directories:

  agent     every history/<n>/ snapshot whose RTL was the buggy file and where a test function failed
            (target original, or working before any edit). Identical snapshots replay once.
  baseline  the optional test in the submission (submission/tests/test_baseline.py), written without
  bestof    ever being run; for best-of-k, the selected candidate's.

Each candidate is replayed twice, each time in a fresh sandbox (no network, read-only workspace,
same limits as the tool server) holding only <top>.v and the test files: once with the buggy RTL,
once with designs/<design>/golden.v as <top>.v. Same module, test filter and seed as the run.
A run EXPOSES its bug if one test function fails on buggy in the replay (and, for the agent, also
failed in the run itself) and the same function passes on golden. A golden build failure, crash
or timeout is not a pass. Writes <run>/exposure.json; finished runs are skipped unless --force.
For the agent this is Metric B (executed exposure); the baselines never run tests, so for them
it is Metric A (test exposure capability) directly.

--final (Metric A for the agent): replays the agent's final test set instead, every module in
submission/tests/ whether it ever ran or not, with no "failed in the run" condition, so all arms
are scored by the same rule on the tests they leave behind. Writes <run>/exposure_final.json.

  .venv/bin/python tools/replay_exposure.py runs/eval-haiku runs/eval-haiku-bestof [--workers 6]
  .venv/bin/python tools/replay_exposure.py --final runs/eval-haiku
"""

import argparse
import hashlib
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from toolserver.sandbox import Sandbox, remove_leftovers  # noqa: E402
from toolserver.server import TOOL_TIMEOUT, _box_result, _sha, load_bug  # noqa: E402
from toolserver.workspace import TEST_NAME  # noqa: E402

BASELINE_SEED = 1   # baseline tests never ran, so they have no run seed; any fixed one will do


def test_files(d: Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(d.iterdir())
            if TEST_NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink()}


def final_candidates(run_dir: Path) -> list[dict]:
    """The agent's submitted tests, one candidate per module."""
    tests = run_dir / "submission" / "tests"
    files = test_files(tests) if tests.is_dir() else {}
    return [{"source": "submission", "files": files, "module": name.removesuffix(".py"), "testcase": None,
             "failed_in_run": None} for name in files]


def candidates(run_dir: Path, bug: dict) -> list[dict]:
    """What to replay: [{"source", "files", "module", "testcase", "failed_in_run"}]."""
    if run_dir.name.startswith("agent-"):
        buggy_sha = _sha((ROOT / bug["file"]).read_text())
        trace = run_dir / "trace.jsonl"
        args = {}
        for line in trace.read_text().splitlines() if trace.exists() else []:
            e = json.loads(line)
            if e["tool"] == "run_cocotb" and e.get("ok"):
                args[e["result"]["history"]] = e["args"]
        out, seen = [], set()
        for res_file in sorted((run_dir / "history").glob("*/_result.json")):
            r = json.loads(res_file.read_text())
            failed = [t["name"] for t in r["tests"] if not t["passed"] and not t.get("skipped")]
            if r["rtl_sha256"] != buggy_sha or not failed or r["history"] not in args:
                continue
            a = args[r["history"]]
            module = a["test_file"].removeprefix("tests/").removesuffix(".py")
            files = test_files(res_file.parent)
            key = (json.dumps(files, sort_keys=True), module, a.get("testcase"))
            if key in seen:
                continue
            seen.add(key)
            out.append({"source": r["history"], "files": files, "module": module,
                        "testcase": a.get("testcase"), "failed_in_run": failed})
        return out
    tests = run_dir / "submission" / "tests"
    if not (tests / "test_baseline.py").exists():
        return []
    return [{"source": "submission", "files": test_files(tests), "module": "test_baseline",
             "testcase": None, "failed_in_run": None}]


def replay(work: Path, top: str, rtl: str, cand: dict, seed: int) -> dict:
    """One sandboxed cocotb run. Returns {"status", "failed", "passed"} (function names)."""
    if work.exists():
        shutil.rmtree(work)
    (work / "tests").mkdir(parents=True)
    (work / f"{top}.v").write_text(rtl)
    for name, text in cand["files"].items():
        (work / "tests" / name).write_text(text)
    try:
        with Sandbox(work) as box:
            rc, out, killed = box.exec(
                ["python", "/opt/box/box_runner.py", "cocotb", "--rtl", f"/ws/{top}.v", "--top", top,
                 "--module", cand["module"], "--seed", str(seed), "--build", "/tmp/build"]
                + (["--testcase", cand["testcase"]] if cand["testcase"] else []), TOOL_TIMEOUT)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    res = None if killed else _box_result(out)
    status = "timeout" if killed else "crash" if res is None else res["status"]
    tests = res["tests"] if res else []
    return {"status": status,
            "failed": [t["name"] for t in tests if not t["passed"] and not t.get("skipped")],
            "passed": [t["name"] for t in tests if t["passed"]]}


def replay_run(run_dir: Path, force: bool, final: bool = False) -> dict | None:
    out = run_dir / ("exposure_final.json" if final else "exposure.json")
    if out.exists() and not force:
        return json.loads(out.read_text())
    info = json.loads((run_dir / "run.json").read_text())
    bug = load_bug(info["bug"])
    top = bug["top"]
    buggy = (ROOT / bug["file"]).read_text()
    golden = (ROOT / "designs" / bug["design"] / "golden.v").read_text()
    agent = run_dir.name.startswith("agent-")
    seed = info.get("seed", BASELINE_SEED) if agent else BASELINE_SEED
    replays = []
    for i, cand in enumerate(final_candidates(run_dir) if final else candidates(run_dir, bug)):
        b = replay(run_dir / "_replay" / f"{i}-buggy", top, buggy, cand, seed)
        g = replay(run_dir / "_replay" / f"{i}-golden", top, golden, cand, seed)
        fails_buggy = [n for n in b["failed"] if cand["failed_in_run"] is None or n in cand["failed_in_run"]]
        replays.append({"source": cand["source"], "module": cand["module"], "testcase": cand["testcase"],
                        "files": sorted(cand["files"]), "failed_in_run": cand["failed_in_run"],
                        "buggy": b, "golden": g, "exposing": [n for n in fails_buggy if n in g["passed"]],
                        "confirmed_on_buggy": bool(fails_buggy)})
    shutil.rmtree(run_dir / "_replay", ignore_errors=True)
    result = {"run": run_dir.name, "bug": bug["id"], "seed": seed, "final_tests": final, "has_test": bool(replays),
              "confirmed_on_buggy": any(r["confirmed_on_buggy"] for r in replays),
              "exposed": any(r["exposing"] for r in replays), "replays": replays}
    out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs_dirs", type=Path, nargs="+")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true", help="replay runs that already have a result")
    ap.add_argument("--final", action="store_true", help="agent runs only: replay the final submitted tests")
    a = ap.parse_args()
    arms = ("agent",) if a.final else ("agent", "baseline", "bestof")
    runs = sorted(r for d in a.runs_dirs for r in d.iterdir()
                  if (r / "run.json").exists() and r.name.split("-")[0] in arms)
    remove_leftovers()
    try:
        with ThreadPoolExecutor(a.workers) as pool:
            for r in pool.map(lambda d: replay_run(d, a.force, a.final), runs):
                print(f"{r['run']:<40} test={r['has_test']!s:<5} buggy={r['confirmed_on_buggy']!s:<5} "
                      f"exposed={r['exposed']!s:<5} ({len(r['replays'])} replayed)", flush=True)
    finally:
        remove_leftovers()


if __name__ == "__main__":
    main()
