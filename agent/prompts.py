"""Prompt text shared by the agent and the single-shot baseline.

Both arms get exactly the same task context (the spec and the numbered buggy file, numbered the
way read_file numbers it), so any difference in results comes from the tool loop, not the inputs.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def numbered(text: str) -> str:
    lines = text.splitlines()
    width = len(str(len(lines)))
    return "\n".join(f"{i:>{width}}| {l}" for i, l in enumerate(lines, 1))


def task_context(bug: dict) -> str:
    top = bug["top"]
    spec = (ROOT / "designs" / bug["design"] / "spec.md").read_text().strip()
    rtl = (ROOT / bug["file"]).read_text()
    return (f"The design `{top}` has one bug. Its spec (spec.md):\n\n{spec}\n\n"
            f"The buggy RTL ({top}.v, numbered as in original/{top}.v):\n\n{numbered(rtl)}")


AGENT_GUIDE = """\
How to work:
- Read the spec, write cocotb tests that check what it requires, and run them on the original
  file to find behavior that breaks the spec. Then find the line responsible, fix the working
  file, lint it, and rerun your tests on it before you submit.
- Before each tool call, say in a sentence or two what you observed and what you will check next.
  When a test fails, say whether you think the design or your test is wrong, and why.
- Change only what the bug needs; keep the module's ports and behavior otherwise identical.
- cocotb 2.0 basics: `import cocotb`; `from cocotb.clock import Clock`;
  `from cocotb.triggers import RisingEdge, FallingEdge, Timer`; tests are `@cocotb.test()` async
  functions taking `dut`; start a clock with `Clock(dut.clk, 10, unit="ns").start()`; set inputs
  with `dut.x.value = 1`; wait with `await Timer(1, unit="ns")`; read with `int(dut.y.value)`.
- Your budget is small: don't spend calls rereading files you have already seen."""


# Phase 6d ablation: the same guide without simulation. Only the parts that need run_cocotb change:
# the first bullet (same structure, "review" for "rerun your tests"), and the failing-test sentence
# and the cocotb basics are dropped. Everything else is AGENT_GUIDE verbatim; no new strategy.
_SIM_FIRST = """\
- Read the spec, write cocotb tests that check what it requires, and run them on the original
  file to find behavior that breaks the spec. Then find the line responsible, fix the working
  file, lint it, and rerun your tests on it before you submit."""
_NOSIM_FIRST = """\
- Read the spec and the original file to find behavior that breaks the spec. Then find the line
  responsible, fix the working file, lint it, and review it before you submit."""
_SIM_FAILING = "\n  When a test fails, say whether you think the design or your test is wrong, and why."
_SIM_BASICS = AGENT_GUIDE[AGENT_GUIDE.index("- cocotb 2.0 basics:"):AGENT_GUIDE.index("- Your budget is small")]
assert _SIM_FIRST in AGENT_GUIDE and _SIM_FAILING in AGENT_GUIDE and _SIM_BASICS
AGENT_GUIDE_NOSIM = (AGENT_GUIDE.replace(_SIM_FIRST, _NOSIM_FIRST).replace(_SIM_FAILING, "")
                     .replace(_SIM_BASICS, ""))


def agent_messages(instructions: str, bug: dict, sim: bool = True) -> list[dict]:
    guide = AGENT_GUIDE if sim else AGENT_GUIDE_NOSIM
    return [{"role": "system", "content": f"{instructions}\n\n{guide}"},
            {"role": "user", "content": task_context(bug) + "\n\nFind and fix the bug, then call submit_patch."}]


BASELINE_SYSTEM = """\
You are debugging one Verilog design that has a bug. You get the spec and the buggy RTL. You can't
run anything: answer in one reply.
Reply with one JSON object and nothing else:
{
  "line": <number of the buggy line, as numbered in the given file>,
  "explanation": "<what is wrong, which behavior in the spec it breaks, and how you fixed it>",
  "patched_file": "<the complete fixed Verilog file>",
  "test": "<optional: a cocotb 2.0 test module (Python) that fails on the buggy file and passes on the fix>"
}
Change only what the bug needs; keep the module's ports and behavior otherwise identical.
cocotb 2.0 basics: `import cocotb`; `from cocotb.clock import Clock`;
`from cocotb.triggers import RisingEdge, FallingEdge, Timer`; tests are `@cocotb.test()` async
functions taking `dut`; start a clock with `Clock(dut.clk, 10, unit="ns").start()`."""


def baseline_messages(bug: dict) -> list[dict]:
    return [{"role": "system", "content": BASELINE_SYSTEM},
            {"role": "user", "content": task_context(bug)}]


SELECTOR_SYSTEM = """\
You are reviewing candidate fixes for one Verilog design that has a bug. You get the spec, the buggy
RTL and several candidate patches (unified diffs against the buggy file), each with the line its
author blames and their explanation. You can't run anything: answer in one reply.
Pick the candidate most likely to make the design meet its spec without changing anything else.
Reply with one JSON object and nothing else:
{"choice": <candidate number>, "reason": "<one or two sentences>"}"""


def selector_messages(bug: dict, candidates: list[dict]) -> list[dict]:
    """candidates: [{"line", "explanation", "diff"}], shown as candidates 1..n in the given order."""
    parts = [task_context(bug)]
    for i, c in enumerate(candidates, 1):
        parts.append(f"Candidate {i} (blames line {c['line']}):\n{c['explanation']}\n\n```diff\n{c['diff']}```")
    return [{"role": "system", "content": SELECTOR_SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)}]
