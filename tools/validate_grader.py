"""Grader validation: runs the equivalence grader on labeled variants and checks every verdict.

Each suite in grader/validation/<suite>/ has a suite.json (golden RTL, meta.json, optional
reference-test design) and variant files. Expected verdicts come from the file name
(bug_* -> FAIL, eq_* -> PASS) or from suite.json's "special" entries.

Labels are cross-checked independently of the formal grader:
  eq_*  must pass the hidden reference test (if the suite has one) AND show no mismatch in a
        random differential simulation against golden (same validity masks, random resets)
  bug_* must fail the reference test OR show a mismatch in that simulation
A case is OK only if the grader's verdict matches and its label cross-check holds.
Runs inside the container (see `make grader-validate`). Optional arguments limit the suites.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from grader.equiv import _gold_expr, check_equivalence, ports_of  # noqa: E402
from grader.ref_runner import run_reference  # noqa: E402

VALIDATION = ROOT / "grader" / "validation"
BUILD = ROOT / "build" / "grader_validation"
SIM_CYCLES = 10000


def _rand(width):
    """A Verilog expression giving `width` random bits."""
    return "{" + ", ".join(["$random(seed)"] * ((width + 31) // 32)) + "}"


def random_sim(grade_dir: Path, meta: dict, cycles=SIM_CYCLES, seed=1) -> int | None:
    """Simulates the grader's prepared gold/gate netlists side by side on random inputs and
    returns the number of compared outputs that differed (None if the simulation failed)."""
    gold = json.loads((grade_dir / "gold.json").read_text())["modules"][meta["top"]]
    ports = ports_of(gold)
    inputs = {n: w for n, (d, w) in ports.items() if d == "input"}
    outputs = {n: w for n, (d, w) in ports.items() if d == "output"}
    rules = meta.get("compare") or {}
    sequential = meta["kind"] == "sequential"
    clk = meta["clock"] if sequential else None
    rst = meta["reset"]["port"] if sequential else None
    on = ("1'b1" if meta["reset"]["active"] == "high" else "1'b0") if sequential else None

    driven = [n for n in inputs if n not in (clk, rst)]
    randomize = [f"        {n} = {_rand(inputs[n])};" for n in driven]
    compare = []
    for n in outputs:
        valid = _gold_expr(rules[n]["valid_when"], inputs, outputs) if n in rules else "1'b1"
        compare.append(
            f"        if (({valid}) && (g__{n} !== t__{n})) begin mism = mism + 1;\n"
            f"            if (mism <= 3) $display(\"mismatch cycle %0d {n}: gold=%h gate=%h\", cyc, g__{n}, t__{n}); end")
    conns = lambda side: ", ".join([f".{n}({n})" for n in inputs] + [f".{n}({side}__{n})" for n in outputs])

    tb = ["`timescale 1ns/1ps", "module tb;"]
    tb += [f"    reg [{w - 1}:0] {n};" for n, w in inputs.items()]
    tb += [f"    wire [{w - 1}:0] {s}__{n};" for s in ("g", "t") for n, w in outputs.items()]
    tb += [f"    gold u_gold ({conns('g')});", f"    gate u_gate ({conns('t')});",
           "    integer cyc, mism, seed;", "    initial begin", f"        seed = {seed}; mism = 0;"]
    if sequential:
        # Reset in cycle 0, like the miter; afterwards reset is a random input (about 1 in 64).
        tb += randomize + [f"        {clk} = 0; {rst} = {on};", f"        #5 {clk} = 1; #5 {clk} = 0;",
                           f"        for (cyc = 1; cyc <= {cycles}; cyc = cyc + 1) begin"]
        tb += ["    " + r for r in randomize]
        tb += [f"            {rst} = (($random(seed) & 63) == 0) ? {on} : ~{on};", "            #1;"]
        tb += ["    " + c.replace("\n", "\n    ") for c in compare]
        tb += [f"            #4 {clk} = 1; #5 {clk} = 0;", "        end"]
    else:
        tb += [f"        for (cyc = 1; cyc <= {cycles}; cyc = cyc + 1) begin"]
        tb += ["    " + r for r in randomize] + ["            #1;"]
        tb += ["    " + c.replace("\n", "\n    ") for c in compare] + ["            #1;", "        end"]
    tb += ['        $display("MISMATCHES %0d", mism);', "        $finish;", "    end", "endmodule", ""]

    sim = grade_dir / "sim"
    sim.mkdir(exist_ok=True)
    (sim / "tb.v").write_text("\n".join(tb))
    steps = [["yosys", "-q", "-p", "read_rtlil ../gold.il; read_rtlil ../gate.il; write_verilog -noattr models.v"],
             ["iverilog", "-g2012", "-o", "sim.vvp", "tb.v", "models.v"],
             ["vvp", "-n", "sim.vvp"]]
    for cmd in steps:
        proc = subprocess.run(cmd, cwd=sim, capture_output=True, text=True, timeout=600)
        (sim / f"{cmd[0]}.log").write_text(proc.stdout + proc.stderr)
        if proc.returncode != 0:
            return None
    lines = [l for l in proc.stdout.splitlines() if l.startswith("MISMATCHES")]
    return int(lines[-1].split()[1]) if lines else None


def run_suite(suite: Path) -> list[dict]:
    cfg = json.loads((suite / "suite.json").read_text())
    gold = ROOT / cfg["golden"]
    base_meta = json.loads((ROOT / cfg["meta"]).read_text())
    ref_design = ROOT / cfg["ref_design"] if cfg.get("ref_design") else None
    special = cfg.get("special", {})
    rows = []
    for gate in sorted(suite.glob("*.v")):
        name = gate.stem
        spec = special.get(name, {})
        expect = spec.get("expect") or ("FAIL" if name.startswith("bug_") else
                                        "PASS" if name.startswith("eq_") else None)
        if expect is None:
            raise SystemExit(f"{suite.name}/{gate.name}: no expected verdict (name it bug_*/eq_* or add to special)")
        meta = {**base_meta, **spec.get("meta_override", {})}
        out = BUILD / suite.name / name
        r = check_equivalence(gold, gate, meta, out)

        problems = []
        if r.verdict != expect:
            problems.append(f"verdict {r.verdict}, expected {expect}: {r.reason}")
        if spec.get("reason_contains") and spec["reason_contains"] not in r.reason:
            problems.append(f"reason {r.reason!r} lacks {spec['reason_contains']!r}")

        ref = sim = "-"
        if spec.get("check_label", not spec):
            if ref_design:
                tests, failed = run_reference(ref_design, gate, out / "ref")
                ref = "pass" if tests and not failed else "fail"
            mism = random_sim(out, meta) if (out / "gate.il").exists() else None
            sim = "error" if mism is None else str(mism)
            if expect == "PASS":
                if ref == "fail":
                    problems.append("label check: equivalent variant fails the reference test")
                if mism != 0:
                    problems.append(f"label check: random simulation mismatches = {sim}")
            elif ref != "fail" and not mism:
                problems.append("label check: neither the reference test nor random simulation sees the bug")
        rows.append({"suite": suite.name, "case": name, "expect": expect, "verdict": r.verdict,
                     "ref": ref, "sim": sim, "eqy": r.eqy_sby or "-", "disagree": r.disagreement,
                     "secs": r.elapsed_s, "cex_step": r.cex_step, "problems": problems})
    return rows


def main():
    names = sys.argv[1:] or sorted(p.parent.name for p in VALIDATION.glob("*/suite.json"))
    rows = []
    print(f"{'case':<36} {'expect':<12} {'verdict':<12} {'ref':<5} {'simΔ':<6} {'eqy-sby':<8} {'secs':>5}  cex")
    for name in names:
        for row in run_suite(VALIDATION / name):
            rows.append(row)
            flag = "" if not row["problems"] else "  <-- " + "; ".join(row["problems"])
            secs = f"{row['secs']:.2f}" if row["secs"] is not None else "-"
            eqy = row["eqy"] + ("*" if row["disagree"] else "")
            print(f"{row['suite'] + '/' + row['case']:<36} {row['expect']:<12} {row['verdict']:<12} "
                  f"{row['ref']:<5} {row['sim']:<6} {eqy:<8} {secs:>5}  {'-' if row['cex_step'] is None else row['cex_step']}{flag}")

    bad = [r for r in rows if r["problems"]]
    false_pass = [r for r in rows if r["verdict"] == "PASS" and r["expect"] != "PASS"]
    false_fail = [r for r in rows if r["verdict"] == "FAIL" and r["expect"] == "PASS"]
    inconclusive = [r for r in rows if r["verdict"] == "INCONCLUSIVE" and r["expect"] != "INCONCLUSIVE"]
    disagree = [r for r in rows if r["disagree"]]
    times = [r["secs"] for r in rows if r["secs"] is not None]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} cases OK | false PASS {len(false_pass)} | "
          f"false FAIL {len(false_fail)} | unexpected INCONCLUSIVE {len(inconclusive)} | "
          f"label-check problems {sum(any(p.startswith('label') for p in r['problems']) for r in rows)}")
    print(f"PDR time: max {max(times):.2f}s over {len(times)} proofs" if times else "no proofs ran")
    print(f"EQY-sby disagreements (marked *, diagnostic only): "
          f"{', '.join(r['suite'] + '/' + r['case'] for r in disagree) or 'none'}")
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
