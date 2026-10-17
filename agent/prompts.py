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


def agent_messages(instructions: str, bug: dict) -> list[dict]:
    return [{"role": "system", "content": f"{instructions}\n\n{AGENT_GUIDE}"},
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
