"""Formal equivalence grader: is a patched design externally equivalent to the golden one?

Builds a whole-design miter (golden and patch side by side, same inputs, reset applied in
cycle 0) and asks SBY's PDR engine to prove every output equal from then on. An output with a
benchmark-defined `valid_when` rule in meta.json is only compared while the GOLDEN design says
it is valid, so a buggy patch can't mask its own outputs. Only ports are compared: a patch may
rename or re-encode internal state.

Verdicts:
  PASS          PDR proved equivalence, and the reachability check showed the proof isn't vacuous
  FAIL          PDR found a counterexample from reset (even if SBY then failed to write its
                trace), or the patch is invalid (doesn't
                elaborate, wrong ports, a clock or clock edge golden doesn't use, forbidden
                constructs)
  INCONCLUSIVE  timeout, unknown, or an unreachable reset/validity condition; earns no credit
  ERROR         the grader itself broke (e.g. golden failed to elaborate); rerun, don't score

EQY (sby strategy) also runs as a diagnostic. It never changes the verdict; a conclusive EQY
result that differs from a conclusive PDR result is flagged as a disagreement.

Usage (inside the container):
  python -m grader.equiv --design designs/token_bucket --gate patch.v --work build/grade/x
  python -m grader.equiv --gold smoke/fifo.v --meta smoke/meta.json --gate smoke/fifo_bad.v --work ...
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

PROVE_TIMEOUT = 60  # default seconds for the PDR proof; meta.json `prove_timeout` overrides it
COVER_DEPTH = 20     # cycles the reachability check may search

# Cells a patch must not contain: they would let it constrain or fake the proof.
FORMAL_CELLS = {"$check", "$assert", "$assume", "$cover", "$live", "$fair", "$anyconst",
                "$anyseq", "$allconst", "$allseq", "$anyinit", "$initstate", "$equiv"}
# Preprocessor directives a patch must not use: `include could read the golden file at grading
# time, and conditional compilation could behave differently under formal (FORMAL/SYNTHESIS
# defines) than in simulation.
FORBIDDEN_DIRECTIVE = re.compile(r"`(include|ifdef|ifndef|elsif)\b")
COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
# valid_when tokens: Verilog number literals pass through, identifiers must be port names.
TOKEN = re.compile(r"\d*'[sS]?[bodhBODH][0-9a-fA-F_xXzZ?]+|\d+|[A-Za-z_][A-Za-z0-9_$]*")


@dataclass
class Result:
    verdict: str                      # PASS / FAIL / INCONCLUSIVE / ERROR
    reason: str
    failing_outputs: list[str] = field(default_factory=list)
    cex_step: int | None = None       # cycle of the first mismatch (reset is cycle 0)
    cex_trace: str | None = None
    elapsed_s: float | None = None    # PDR proof time
    eqy_sby: str | None = None        # diagnostic verdict
    disagreement: bool = False


class GraderError(Exception):
    """The grader itself failed; the run should be repeated, not scored."""


def _run(cmd, cwd, log: Path, timeout):
    """Runs cmd, saving output to log. Returns (exit code, output); exit code None on timeout."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out, rc = proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        partial = [s.decode(errors="replace") if isinstance(s, bytes) else s or "" for s in (e.stdout, e.stderr)]
        out, rc = "".join(partial) + f"\nTIMEOUT after {timeout}s", None
    log.write_text(out)
    return rc, out


def _sby_status(log_text):
    m = re.findall(r"DONE \((PASS|FAIL|UNKNOWN|TIMEOUT|ERROR)", log_text)
    return m[-1] if m else "ERROR"


def _prove_status(log_text):
    """SBY status of the PDR proof, plus FAIL_NO_TRACE: PDR found a counterexample, then SBY
    crashed turning it into a trace. Seen with patches that read an out-of-range bit: the AIGER
    model PDR proves on and the SMT2 model the trace is replayed on treat the undefined bit
    differently. The proof result stands; only the explanation is lost. Any other crash, including
    one inside PDR itself, stays ERROR."""
    status = _sby_status(log_text)
    if (status == "ERROR" and "engine_0 (abc pdr) returned FAIL" in log_text
            and "engine_0 did not produce any traces" in log_text):
        return "FAIL_NO_TRACE"
    return status


def prepare(rtl: Path, top: str, name: str, out: Path) -> dict:
    """Elaborates and flattens one design, renames its top to `name`, and writes
    <name>.il (for the miter), <name>_eqy.il (original top name, for EQY) and <name>.json.
    Returns the parsed JSON netlist. Raises ValueError if the design doesn't elaborate."""
    script = (f"read_verilog -formal {rtl}; hierarchy -check -top {top}; proc; flatten; "
              f"hierarchy -top {top}; prep -top {top}; memory_map; opt_clean; "
              f"write_rtlil {name}_eqy.il; write_json {name}.json; "
              f"rename {top} {name}; write_rtlil {name}.il")
    rc, text = _run(["yosys", "-q", "-p", script], out, out / f"{name}_prep.log", 120)
    if rc != 0:
        err = next((l for l in text.splitlines() if "ERROR" in l), text.strip()[-300:])
        raise ValueError(f"does not elaborate: {err.strip()}")
    return json.loads((out / f"{name}.json").read_text())["modules"][top]


def ports_of(netlist: dict) -> dict[str, tuple[str, int]]:
    return {n: (p["direction"], len(p["bits"])) for n, p in netlist["ports"].items()}


def clocking(netlist: dict) -> set[tuple[str, int]]:
    """Returns the (clock, edge) pairs the design's flip-flops use: clock is a port name (or
    "internal" for a derived clock), edge is 1 for posedge and 0 for negedge."""
    bit_names = {b: n for n, p in netlist["ports"].items() for b in p["bits"]}
    pairs = set()
    for cell in netlist["cells"].values():
        if "CLK" in cell["connections"] and "CLK_POLARITY" in cell["parameters"]:
            bit = cell["connections"]["CLK"][0]
            pairs.add((bit_names.get(bit, "internal"), int(str(cell["parameters"]["CLK_POLARITY"]), 2)))
    return pairs


def _check_patch_source(rtl: Path):
    """Returns a reason string if the patch uses forbidden directives, else None."""
    text = COMMENTS.sub("", rtl.read_text(errors="replace"))
    m = FORBIDDEN_DIRECTIVE.search(text)
    return f"forbidden construct: `{m.group(1)}" if m else None


def _gold_expr(expr: str, inputs, outputs) -> str:
    """Rewrites a valid_when expression so output names read the golden design's outputs."""
    def sub(m):
        t = m.group(0)
        if t[0].isdigit() or t[0] == "'":
            return t
        if t in outputs:
            return f"g__{t}"
        if t in inputs:
            return t
        raise ValueError(f"valid_when uses {t!r}, which is not a port")
    return TOKEN.sub(sub, expr)


def build_miter(ports: dict, meta: dict) -> tuple[str, dict, dict]:
    """Returns (miter Verilog, assert line -> output name, cover line -> description)."""
    inputs = {n: w for n, (d, w) in ports.items() if d == "input"}
    outputs = {n: w for n, (d, w) in ports.items() if d == "output"}
    rules = meta.get("compare") or {}
    unknown = set(rules) - set(outputs)
    if unknown:
        raise ValueError(f"compare rules name non-outputs: {sorted(unknown)}")
    sequential = meta["kind"] == "sequential"

    lines = ["// Generated by grader/equiv.py: golden vs patch, same inputs, outputs compared after reset.",
             "module miter_top ("]
    # One list entry per line: asserts/covers are identified by their line number.
    decls = [f"    input [{w - 1}:0] {n}" for n, w in inputs.items()]
    lines += [d + "," for d in decls[:-1]] + decls[-1:] + [");"]
    for side in ("g", "t"):
        lines += [f"    wire [{w - 1}:0] {side}__{n};" for n, w in outputs.items()]
    for side, mod in (("g", "gold"), ("t", "gate")):
        conns = [f".{n}({n})" for n in inputs] + [f".{n}({side}__{n})" for n in outputs]
        lines.append(f"    {mod} u_{mod} ({', '.join(conns)});")

    if sequential:
        clk, rst = meta["clock"], meta["reset"]
        level = "1'b1" if rst["active"] == "high" else "1'b0"
        lines += ["    reg m__in_reset = 1'b1;",
                  f"    always @(posedge {clk}) m__in_reset <= 1'b0;",
                  f"    always @* if (m__in_reset) assume ({rst['port']} == {level});"]
    else:
        lines.append("    wire m__in_reset = 1'b0;")

    asserts, covers = {}, {}
    lines.append("`ifndef REACH")
    for n in outputs:
        cond = "!m__in_reset"
        if n in rules:
            cond += f" && ({_gold_expr(rules[n]['valid_when'], inputs, outputs)})"
        lines.append(f"    always @* if ({cond}) assert (g__{n} == t__{n});")
        asserts[len(lines)] = n
    lines.append("`else")
    lines.append("    always @* cover (!m__in_reset);")
    covers[len(lines)] = "past reset"
    for n, rule in rules.items():
        lines.append(f"    always @* cover (!m__in_reset && ({_gold_expr(rule['valid_when'], inputs, outputs)}));")
        covers[len(lines)] = f"{n} valid_when {rule['valid_when']!r}"
    lines += ["`endif", "endmodule", ""]
    return "\n".join(lines), asserts, covers


def _sby_file(mode_opts: str, engine: str, defines: str) -> str:
    return (f"[options]\n{mode_opts}\n\n[engines]\n{engine}\n\n[script]\n"
            f"read_rtlil gold.il\nread_rtlil gate.il\nread_verilog -formal {defines} miter.sv\n"
            f"prep -top miter_top\n\n[files]\ngold.il\ngate.il\nmiter.sv\n")


def _run_eqy(top: str, work: Path, timeout: int) -> str:
    (work / "eqy.eqy").write_text(
        f"[gold]\nread_rtlil gold_eqy.il\nprep -top {top}\n\n"
        f"[gate]\nread_rtlil gate_eqy.il\nprep -top {top}\n\n"
        "[strategy sby]\nuse sby\ndepth 10\nengine smtbmc\n")
    rc, text = _run(["eqy", "-f", "eqy.eqy", "-d", "eqy"], work, work / "eqy.log", timeout)
    if rc is None:
        return "TIMEOUT"
    m = re.findall(r"DONE \((PASS|FAIL|UNKNOWN|ERROR)", text)
    return m[-1] if m else "ERROR"


def check_equivalence(gold_rtl, gate_rtl, meta: dict, work_dir, timeout=None,
                      run_eqy=True) -> Result:
    """Grades gate_rtl against gold_rtl. Writes artifacts and result.json into work_dir.
    The proof timeout is `timeout` if given, else the design's `prove_timeout`, else PROVE_TIMEOUT."""
    timeout = timeout or meta.get("prove_timeout", PROVE_TIMEOUT)
    gold_rtl, gate_rtl, work = Path(gold_rtl).resolve(), Path(gate_rtl).resolve(), Path(work_dir)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        result = _grade(gold_rtl, gate_rtl, meta, work, timeout, run_eqy)
    except GraderError as e:
        result = Result("ERROR", str(e))
    (work / "result.json").write_text(json.dumps(asdict(result), indent=2) + "\n")
    return result


def _grade(gold_rtl, gate_rtl, meta, work, timeout, run_eqy) -> Result:
    top = meta["top"]
    try:
        gold = prepare(gold_rtl, top, "gold", work)
    except ValueError as e:
        raise GraderError(f"golden design: {e}")
    if bad := {c["type"] for c in gold["cells"].values()} & FORMAL_CELLS:
        raise GraderError(f"golden design contains formal cells {sorted(bad)}")

    # The patch: source rules, elaboration, formal cells, interface.
    if reason := _check_patch_source(gate_rtl):
        return Result("FAIL", reason)
    try:
        gate = prepare(gate_rtl, top, "gate", work)
    except ValueError as e:
        return Result("FAIL", f"patch {e}")
    if bad := {c["type"] for c in gate["cells"].values()} & FORMAL_CELLS:
        return Result("FAIL", f"forbidden construct: formal cells {sorted(bad)}")
    gold_ports, gate_ports = ports_of(gold), ports_of(gate)
    if gold_ports != gate_ports:
        diff = sorted(set(gold_ports.items()) ^ set(gate_ports.items()))
        return Result("FAIL", f"interface mismatch: {diff}")
    # The proof steps every flip-flop once per cycle and doesn't model the clock wire, so it
    # can't compare a patch clocked differently (e.g. negedge); SBY would just crash.
    if extra := clocking(gate) - clocking(gold):
        edges = ", ".join(f"{'posedge' if e else 'negedge'} {c}" for c, e in sorted(extra))
        return Result("FAIL", f"clocking differs from golden: patch uses {edges}")

    try:
        miter, asserts, covers = build_miter(gold_ports, meta)
    except ValueError as e:
        raise GraderError(f"meta.json: {e}")
    (work / "miter.sv").write_text(miter)

    # Reachability: reset must complete and every validity condition must be able to hold,
    # otherwise a PASS could be vacuous.
    depth = meta.get("cover_depth", COVER_DEPTH)
    (work / "cover.sby").write_text(_sby_file(f"mode cover\ndepth {depth}", "smtbmc", "-DREACH"))
    rc, text = _run(["sby", "-f", "cover.sby"], work, work / "cover.log", timeout + 60)
    status = "TIMEOUT" if rc is None else _sby_status(text)
    if status == "ERROR":
        raise GraderError(f"reachability check crashed (see {work / 'cover.log'})")
    if status != "PASS":
        unreached = text.split("unreached cover statements:", 1)[-1] if status == "FAIL" else ""
        lines = sorted({int(n) for n in re.findall(r"at miter\.sv:(\d+)\.", unreached)})
        what = "unreached " + ", ".join(covers.get(n, f"line {n}") for n in lines) if lines else status
        return Result("INCONCLUSIVE", f"reachability check failed: {what}")

    # The proof.
    (work / "prove.sby").write_text(_sby_file(f"mode prove\ntimeout {timeout}", "abc pdr", ""))
    start = time.monotonic()
    rc, text = _run(["sby", "-f", "prove.sby"], work, work / "prove.log", timeout + 60)
    elapsed = round(time.monotonic() - start, 2)
    status = "TIMEOUT" if rc is None else _prove_status(text)

    if status == "PASS":
        result = Result("PASS", "PDR proved all outputs equivalent from reset", elapsed_s=elapsed)
    elif status == "FAIL":
        # SBY omits "step N" when the counterexample is in the first step (combinational designs).
        fails = re.findall(r"failed assertion \S+ at miter\.sv:(\d+)\.\S+(?: step (\d+))?", text)
        outs = sorted({asserts.get(int(line), f"line {line}") for line, _ in fails})
        step = min(int(s or 0) for _, s in fails) if fails else None
        trace = work / "prove" / "engine_0" / "trace.vcd"
        result = Result("FAIL", f"counterexample from reset: {', '.join(outs) or 'output'} differs",
                        failing_outputs=outs, cex_step=step,
                        cex_trace=str(trace) if trace.exists() else None, elapsed_s=elapsed)
    elif status == "FAIL_NO_TRACE":
        result = Result("FAIL", "counterexample from reset; SBY could not write the trace, so the "
                        "failing outputs and step are unknown", elapsed_s=elapsed)
    elif status in ("UNKNOWN", "TIMEOUT"):
        result = Result("INCONCLUSIVE", f"PDR {status.lower()}", elapsed_s=elapsed)
    else:
        raise GraderError(f"proof crashed (see {work / 'prove.log'})")

    if run_eqy:
        result.eqy_sby = _run_eqy(top, work, timeout)
        result.disagreement = (result.verdict in ("PASS", "FAIL")
                               and result.eqy_sby in ("PASS", "FAIL")
                               and result.eqy_sby != result.verdict)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--design", help="design directory (golden.v + meta.json)")
    ap.add_argument("--gold", help="golden RTL (instead of --design)")
    ap.add_argument("--meta", help="meta.json (instead of --design)")
    ap.add_argument("--gate", required=True, help="patched RTL to grade")
    ap.add_argument("--work", required=True, help="output directory")
    ap.add_argument("--timeout", type=int, help=f"proof timeout (default: meta.json prove_timeout, else {PROVE_TIMEOUT})")
    ap.add_argument("--no-eqy", action="store_true", help="skip the EQY diagnostic")
    args = ap.parse_args()
    if args.design:
        gold, meta = Path(args.design) / "golden.v", Path(args.design) / "meta.json"
    elif args.gold and args.meta:
        gold, meta = Path(args.gold), Path(args.meta)
    else:
        ap.error("give --design, or both --gold and --meta")
    r = check_equivalence(gold, args.gate, json.loads(meta.read_text()), args.work,
                          args.timeout, not args.no_eqy)
    print(f"{r.verdict}: {r.reason}")
    if r.eqy_sby:
        print(f"eqy-sby (diagnostic): {r.eqy_sby}{'  [DISAGREES]' if r.disagreement else ''}")
    sys.exit(2 if r.verdict == "ERROR" else 0)


if __name__ == "__main__":
    main()
