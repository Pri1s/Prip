"""Simulation-side checks on a mutant, run in Icarus next to the grader's formal result.

check_in_simulation() builds one testbench with four copies of the design:
  G  golden source RTL       M  mutant source RTL
  H  golden netlist          N  mutant netlist   (the grader's flattened Yosys models)
and drives them with (1) the formal counterexample's inputs, step by step, then (2) a reset and
random inputs. Registers start at X, as in any simulation; formal let them start anywhere.

It reports:
  replay   first step where G and M differ on a compared output during the counterexample
           (G must be fully defined there; an X on M counts and is flagged). If none, the
           counterexample did not reproduce in simulation.
  simsynth cycles where M's source simulation and M's netlist disagree while both are fully
           defined: the mutant means different things to the simulator and to synthesis
           (e.g. a blocking assignment whose effect depends on event ordering). H vs G is the
           same check on golden, which must be clean.
"""

import json
import re
import subprocess
from pathlib import Path

from grader.equiv import _gold_expr, ports_of

RANDOM_CYCLES = 2000
SIM_TIMEOUT = 60


def read_witness(path: Path) -> list[dict[str, int]]:
    """Top-level input values per step from a Yosys witness (.yw) file."""
    w = json.loads(Path(path).read_text())
    layout, base = [], 0
    for sig in w["signals"]:
        layout.append((sig, base))
        base += sig["width"]
    steps = []
    for st in w["steps"]:
        bits = st["bits"][::-1]   # the string is MSB first; signal offsets count from the LSB
        vals = {}
        for sig, b in layout:
            if len(sig["path"]) == 1 and b + sig["width"] <= len(bits) and not sig["init_only"]:
                chunk = bits[b:b + sig["width"]][::-1]
                vals[sig["path"][0].lstrip("\\")] = int(chunk.replace("x", "0").replace("?", "0"), 2)
        steps.append(vals)
    return steps


def read_vcd(path: Path) -> dict[int, dict[str, str]]:
    """Signal values (binary strings) per formal step from an SBY trace VCD."""
    ids, scope, values, snaps = {}, [], {}, {}
    time = 0
    with open(path) as f:
        for line in f:
            tok = line.split()
            if not tok:
                continue
            if tok[0] == "$scope":
                scope.append(tok[2])
            elif tok[0] == "$upscope":
                scope.pop()
            elif tok[0] == "$var":
                ids.setdefault(tok[3], []).append(".".join(scope + [tok[4]]))
            elif tok[0].startswith("#"):
                snaps[time // 10] = dict(values)
                time = int(tok[0][1:])
            elif tok[0][0] in "01xz" and len(tok) == 1:
                for n in ids.get(tok[0][1:], []):
                    values[n] = tok[0][0]
            elif tok[0][0] == "b":
                for n in ids.get(tok[1], []):
                    values[n] = tok[0][1:]
    snaps[time // 10] = dict(values)
    return snaps


def osdd(vcd: Path, reset_regs: set[str], fail_step: int) -> tuple[int | None, int]:
    """(first step a reset-initialized register differs between golden and mutant, OSDD).
    OSDD = fail_step - divergence + 1, or 0 when no register diverged first (the bug is on a
    combinational path to the output). Registers without a reset value are ignored: the two
    copies start them at independent arbitrary values, which would fake a divergence."""
    snaps = read_vcd(vcd)
    for step in range(1, fail_step + 1):
        vals = snaps.get(step, {})
        for r in sorted(reset_regs):
            g, t = vals.get(f"miter_top.u_gold.{r}"), vals.get(f"miter_top.u_gate.{r}")
            if g is not None and t is not None and "x" not in g + t and int(g, 2) != int(t, 2):
                return step, fail_step - step + 1
    return None, 0


def _rand(width):
    return "{" + ", ".join(["$random(seed)"] * ((width + 31) // 32)) + "}"


def check_in_simulation(grade_dir: Path, golden_rtl: Path, mutant_rtl: Path, meta: dict,
                        witness: list[dict[str, int]] | None, seed: int = 1,
                        cycles: int = RANDOM_CYCLES) -> dict:
    grade_dir = Path(grade_dir)
    top = meta["top"]
    gold = json.loads((grade_dir / "gold.json").read_text())["modules"][top]
    ports = ports_of(gold)
    inputs = {n: w for n, (d, w) in ports.items() if d == "input"}
    outputs = {n: w for n, (d, w) in ports.items() if d == "output"}
    rules = meta.get("compare") or {}
    seq = meta["kind"] == "sequential"
    clk = meta["clock"] if seq else None
    rst = meta["reset"]["port"] if seq else None
    on = ("1'b1" if meta["reset"]["active"] == "high" else "1'b0") if seq else None
    first_cmp = 1 if seq else 0

    def conns(side):
        return ", ".join([f".{n}({n})" for n in inputs] + [f".{n}({side}__{n})" for n in outputs])

    tb = ["`timescale 1ns/1ps", "module tb;"]
    tb += [f"    reg [{w - 1}:0] {n};" for n, w in inputs.items()]
    tb += [f"    wire [{w - 1}:0] {s}__{n};" for s in "gmnh" for n, w in outputs.items()]
    tb += [f"    ref_{top} u_g ({conns('g')});", f"    {top} u_m ({conns('m')});",
           f"    gate u_n ({conns('n')});", f"    gold u_h ({conns('h')});",
           "    integer seed, cyc, rep, ss_m, ss_g, rnd;",
           "    task check(input integer phase, input integer stepno);", "    begin"]
    for n in outputs:
        valid = _gold_expr(rules[n]["valid_when"], inputs, outputs) if n in rules else "1'b1"
        g, m, nn, h = (f"{s}__{n}" for s in "gmnh")
        tb += [f"        if (({valid}) === 1'b1) begin",
               f"            if (phase == 0 && stepno >= {first_cmp} && rep < 0 && ^{g} !== 1'bx && {g} !== {m}) begin",
               f"                rep = stepno; $display(\"REPLAY %0d {n} %0d\", stepno, ^{m} === 1'bx); end",
               f"            if (phase == 1 && stepno >= {first_cmp} && ^{g} !== 1'bx && {g} !== {m}) rnd = rnd + 1;",
               f"            if (^{m} !== 1'bx && ^{nn} !== 1'bx && {m} !== {nn}) begin ss_m = ss_m + 1;",
               f"                if (ss_m <= 3) $display(\"SIMSYNTH mutant phase %0d step %0d {n}: rtl=%h netlist=%h\", phase, stepno, {m}, {nn}); end",
               f"            if (^{g} !== 1'bx && ^{h} !== 1'bx && {g} !== {h}) begin ss_g = ss_g + 1;",
               f"                if (ss_g <= 3) $display(\"SIMSYNTH golden phase %0d step %0d {n}: rtl=%h netlist=%h\", phase, stepno, {g}, {h}); end",
               "        end"]
    tb += ["    end", "    endtask", "    initial begin",
           f"        seed = {seed}; rep = -1; ss_m = 0; ss_g = 0; rnd = 0;"]
    driven = [n for n in inputs if n != clk]
    tick = [f"        #4 {clk} = 1; #5 {clk} = 0;"] if seq else ["        #1;"]
    if seq:
        tb.append(f"        {clk} = 0;")
    for k, vals in enumerate(witness or []):
        tb += [f"        {n} = {inputs[n]}'d{vals.get(n, 0)};" for n in driven]
        tb += [f"        #1 check(0, {k});"] + tick
    # Random phase: reset first (sequential), then random inputs with an occasional reset.
    randomize = [f"            {n} = {_rand(inputs[n])};" for n in driven if n != rst]
    if seq:
        tb += ["        " + r.strip() for r in randomize]
        tb += [f"        {rst} = {on};", "        #1;"] + tick
    tb += [f"        for (cyc = 1; cyc <= {cycles}; cyc = cyc + 1) begin"] + randomize
    if seq:
        tb.append(f"            {rst} = (($random(seed) & 63) == 0) ? {on} : ~{on};")
    tb += ["            #1 check(1, cyc);"] + ["    " + t for t in tick] + ["        end",
           '        $display("DONE rep=%0d ss_m=%0d ss_g=%0d rnd=%0d", rep, ss_m, ss_g, rnd);',
           "        $finish;", "    end", "endmodule", ""]

    sim = grade_dir / "simcheck"
    sim.mkdir(exist_ok=True)
    (sim / "tb.v").write_text("\n".join(tb))
    golden_src = re.sub(rf"\bmodule\s+{re.escape(top)}\b", f"module ref_{top}", Path(golden_rtl).read_text(), count=1)
    (sim / "golden_src.v").write_text(golden_src)
    steps = [["yosys", "-q", "-p", "read_rtlil ../gold.il; read_rtlil ../gate.il; write_verilog -noattr models.v"],
             ["iverilog", "-g2012", "-o", "sim.vvp", "tb.v", "models.v", "golden_src.v", str(Path(mutant_rtl).resolve())],
             ["vvp", "-n", "sim.vvp"]]
    for cmd in steps:
        try:
            proc = subprocess.run(cmd, cwd=sim, capture_output=True, text=True, timeout=SIM_TIMEOUT)
        except subprocess.TimeoutExpired:
            if cmd[0] == "vvp":
                # Every design finishes in seconds; a hang means simulation never settles, e.g. an
                # always @* block that keeps retriggering itself, which synthesis treats as plain logic.
                return {"hang": True}
            return {"error": f"{cmd[0]} timed out"}
        (sim / f"{cmd[0]}.log").write_text(proc.stdout + proc.stderr)
        if proc.returncode != 0:
            return {"error": f"{cmd[0]} failed (see {sim / (cmd[0] + '.log')})"}
    out = proc.stdout
    done = re.search(r"DONE rep=(-?\d+) ss_m=(\d+) ss_g=(\d+) rnd=(\d+)", out)
    if not done:
        return {"error": "simulation did not finish"}
    rep = re.search(r"REPLAY (\d+) (\w+) (\d)", out)
    return {
        "replay_step": int(rep.group(1)) if rep else None,
        "replay_output": rep.group(2) if rep else None,
        "replay_x": bool(int(rep.group(3))) if rep else None,
        "simsynth_mismatches": int(done.group(2)),
        "golden_simsynth_mismatches": int(done.group(3)),
        "random_sim_mismatches": int(done.group(4)),
        "simsynth_examples": re.findall(r"SIMSYNTH mutant [^\n]*", out),
    }
