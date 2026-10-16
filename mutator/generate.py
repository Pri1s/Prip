"""Phase 3a: generate the bug pool. Every golden design is mutated one edit at a time, and each
mutant goes through the same gates; only mutants that pass all of them become benchmark bugs.

  1. lint       compiles under iverilog -g2005, synthesizes, no latches, flops iff sequential
  2. grader     grader/equiv.py (PDR miter). PASS = equivalent mutant, INCONCLUSIVE/ERROR = no
                verdict; only FAIL with a counterexample from reset continues
  3. depth      BMC from reset finds the minimum counterexample depth (PDR's trace can be
                longer); if BMC runs out of time, the depth is stored as bounds
  4. simulation the counterexample is replayed in Icarus on golden vs mutant source, and the
                mutant's source simulation must agree with its own synthesized netlist (no
                simulator-vs-synthesis disagreement, e.g. from event ordering)
  5. reference  the hidden reference test is run; its verdict is metadata
                (reference_test_detected), not a gate

Acceptance (learner's rules): grader FAIL with a counterexample from reset, no sim/synth
disagreement, and either the reference test fails, or it passes and the counterexample replays
as an output mismatch in simulation (then reference_test_detected = false). Grader PASS with any
simulation failure is rejected and listed for investigation; INCONCLUSIVE/ERROR are rejected.
Every rejection is counted in bugs/REPORT.md.

Writes bugs/<design>/<id>.v (agent-visible buggy RTL), bugs/manifest.jsonl (answer key, one line
per accepted bug), bugs/candidates.jsonl (every candidate and its outcome), bugs/REPORT.md.
Runs inside the container (see `make bugs`). Optional arguments limit it to some designs.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from grader.equiv import _sby_file, _sby_status, check_equivalence  # noqa: E402
from mutator.operators import Design, FAMILY, Mutation, enumerate_mutations, localization  # noqa: E402
from mutator.simcheck import check_in_simulation, osdd, read_witness  # noqa: E402
from tools.corpus_check import FLOPS  # noqa: E402

DESIGNS = ROOT / "designs"
BUGS = ROOT / "bugs"
BUILD = ROOT / "build" / "bugs"
BMC_BUDGET = 60        # seconds BMC may spend confirming the minimum depth
REF_TIMEOUT = 600
DEPTH_BINS = [(0, 0, "0"), (1, 2, "1-2"), (3, 5, "3-5"), (6, None, "6+")]
# Outcomes worth keeping work directories for (everything else is reproducible and deleted).
KEEP_WORK = {"rejected_formal_pass_sim_fails", "rejected_simsynth_disagree", "rejected_cex_not_reproduced",
             "error"}


def _run(cmd, cwd, log: Path, timeout):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        out, rc = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        out, rc = f"TIMEOUT after {timeout}s", None
    log.write_text(out)
    return rc, out


def lint(rtl: Path, meta: dict, out: Path) -> str | None:
    """The corpus-check gates. Returns a reason the mutant is stillborn, or None."""
    top, kind = meta["top"], meta["kind"]
    rc, _ = _run(["iverilog", "-g2005", "-Wall", "-o", "lint.vvp", "-s", top, str(rtl)], out, out / "iverilog.log", 60)
    if rc != 0:
        return "does not compile (iverilog -g2005)"
    flop_assert = "select -assert-none" if kind == "combinational" else "select -assert-min 1"
    script = (f"read_verilog {rtl}; hierarchy -check -top {top}; proc; check -assert; "
              f"select -assert-none t:$dlatch t:$adlatch t:$dlatchsr; {flop_assert} {FLOPS}")
    rc, text = _run(["yosys", "-q", "-p", script], out, out / "yosys.log", 120)
    if rc != 0:
        if "dlatch" in text:
            return "infers a latch"
        return "yosys check failed (multiple drivers, undriven wire, logic loop, or comb/seq kind change)"
    return None


def run_reference(design_dir: Path, rtl: Path, out: Path) -> tuple[int, int]:
    """The hidden reference test in a subprocess, so a hung simulation can be timed out."""
    code = ("import json, sys; sys.path.insert(0, sys.argv[4]); from grader.ref_runner import run_reference; "
            "print('REF_RESULT ' + json.dumps(run_reference(sys.argv[1], sys.argv[2], sys.argv[3])))")
    rc, text = _run([sys.executable, "-c", code, str(design_dir), str(rtl), str(out), str(ROOT)],
                    out.parent, out.parent / "ref.log", REF_TIMEOUT)
    m = re.findall(r"REF_RESULT \[(\d+), (\d+)\]", text)
    return (int(m[-1][0]), int(m[-1][1])) if m else (1, 1)   # crash or hang = the test fails


def min_depth(work: Path, pdr_step: int) -> dict:
    """Minimum counterexample depth from reset. BMC tries depth 0, 1, 2, ... so its first
    failure is the minimum; PDR's trace is only an upper bound. Also returns the engine
    directory whose trace (witness + VCD) belongs to that depth."""
    if pdr_step == 0:
        return {"min_depth": 0, "depth_lower": 0, "depth_upper": 0, "depth_exact": True,
                "trace_dir": work / "prove" / "engine_0"}
    (work / "bmc.sby").write_text(_sby_file(f"mode bmc\ndepth {pdr_step + 1}\ntimeout {BMC_BUDGET}", "smtbmc", ""))
    rc, text = _run(["sby", "-f", "bmc.sby"], work, work / "bmc.log", BMC_BUDGET + 120)
    status = "TIMEOUT" if rc is None else _sby_status(text)
    fails = re.findall(r"failed assertion \S+ at miter\.sv:\d+\.\S+(?: step (\d+))?", text)
    if status == "FAIL" and fails:
        step = min(int(s or 0) for s in fails)
        return {"min_depth": step, "depth_lower": step, "depth_upper": step, "depth_exact": True,
                "trace_dir": work / "bmc" / "engine_0"}
    checked = [int(s) for s in re.findall(r"Checking assertions in step (\d+)", text)]
    lower = max(checked) if checked else 1   # steps before the one in progress had no failure
    return {"min_depth": None, "depth_lower": min(lower, pdr_step), "depth_upper": pdr_step,
            "depth_exact": False, "trace_dir": work / "prove" / "engine_0", "bmc_status": status}


def process(task) -> dict:
    """Runs one candidate through every gate. Returns its candidate record."""
    design_dir, cid, m_dict = task
    design_dir = Path(design_dir)
    meta = json.loads((design_dir / "meta.json").read_text())
    golden_rtl = design_dir / "golden.v"
    golden = golden_rtl.read_text()
    m = Mutation(**{**m_dict, "scope": tuple(m_dict["scope"])})
    work = BUILD / design_dir.name / cid
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    mutant = work / f"{meta['top']}.v"
    mutant.write_text(m.apply(golden))
    rec = {"cid": cid, "design": design_dir.name, "operator": m.operator, "family": m.family,
           "note": m.note, "edit": {"golden_span": [m.start, m.end], "original": golden[m.start:m.end],
                                    "replacement": m.replacement},
           "localization": localization(golden, m)}
    started = time.monotonic()
    try:
        _gates(rec, design_dir, meta, golden_rtl, mutant, work)
    except Exception as e:   # a crash in our own pipeline: report it, never accept the mutant
        rec["outcome"], rec["reason"] = "error", f"{type(e).__name__}: {e}"
    rec["seconds"] = round(time.monotonic() - started, 1)
    if rec["outcome"] not in KEEP_WORK:
        shutil.rmtree(work, ignore_errors=True)
    return rec


def _gates(rec, design_dir, meta, golden_rtl, mutant, work):
    if reason := lint(mutant, meta, work):
        rec["outcome"], rec["reason"] = "stillborn", reason
        return
    r = check_equivalence(golden_rtl, mutant, meta, work / "grade", run_eqy=False)
    rec["grader"] = {"verdict": r.verdict, "reason": r.reason, "pdr_cex_step": r.cex_step,
                     "failing_outputs": r.failing_outputs, "proof_s": r.elapsed_s}
    if r.verdict in ("INCONCLUSIVE", "ERROR"):
        rec["outcome"], rec["reason"] = r.verdict.lower(), r.reason
        return
    if r.verdict == "FAIL" and r.cex_step is None:
        rec["outcome"], rec["reason"] = "invalid", r.reason   # e.g. an interface change
        return

    witness = None
    if r.verdict == "FAIL":
        depth = min_depth(work / "grade", r.cex_step)
        trace_dir = depth.pop("trace_dir")
        rec["depth"] = depth
        witness = read_witness(trace_dir / "trace.yw")
        if meta["kind"] == "sequential":
            regs = Design(golden_rtl.read_text()).reset_registers(meta["reset"]["port"])
            fail_step = depth["min_depth"] if depth["depth_exact"] else depth["depth_upper"]
            div, gap = osdd(trace_dir / "trace.vcd", regs, fail_step)
            rec["osdd"] = {"state_divergence_step": div, "osdd": gap, "exact": depth["depth_exact"]}
        else:
            rec["osdd"] = {"state_divergence_step": None, "osdd": 0, "exact": True}

    sim = check_in_simulation(work / "grade", golden_rtl, mutant, meta, witness)
    rec["simulation"] = sim
    if sim.get("hang"):
        rec["outcome"] = "rejected_simsynth_disagree"
        rec["reason"] = ("simulation never settles (the RTL retriggers itself at one time step); "
                         "synthesis treats it as ordinary logic")
        return
    tests, failed = run_reference(design_dir, mutant, work / "ref")
    rec["reference_test"] = {"tests": tests, "failed": failed}
    rec["reference_test_detected"] = bool(failed)

    if "error" in sim:
        rec["outcome"], rec["reason"] = "error", f"simulation check: {sim['error']}"
    elif sim["golden_simsynth_mismatches"]:
        rec["outcome"], rec["reason"] = "error", "golden RTL and golden netlist disagree in simulation"
    elif r.verdict == "PASS":
        if failed or sim["random_sim_mismatches"] or sim["simsynth_mismatches"]:
            rec["outcome"] = "rejected_formal_pass_sim_fails"
            rec["reason"] = (f"grader PASS but reference test failed {failed}/{tests}, "
                             f"random RTL sim mismatches {sim['random_sim_mismatches']}, "
                             f"sim/synth mismatches {sim['simsynth_mismatches']}")
        else:
            rec["outcome"] = "equivalent"
    elif sim["simsynth_mismatches"]:
        rec["outcome"] = "rejected_simsynth_disagree"
        rec["reason"] = f"mutant RTL and its netlist disagree in simulation ({sim['simsynth_mismatches']} cycles)"
    elif sim["replay_step"] is None and not failed:
        # Rule 2: a bug the reference test misses is kept only if the formal counterexample is
        # shown to be a real execution with an output mismatch in simulation.
        rec["outcome"] = "rejected_cex_not_reproduced"
        rec["reason"] = ("reference test passes and the formal counterexample shows no output mismatch "
                         "when replayed in simulation")
    else:
        # The reference test failing is itself a simulation confirmation; a counterexample that
        # doesn't replay (it relied on a register's arbitrary start value, which is X in
        # simulation) is recorded, not rejected.
        rec["outcome"] = "accepted"


def design_info(design_dir: Path) -> dict:
    """Golden sanity (grader PASSes golden vs itself) and size covariates."""
    meta = json.loads((design_dir / "meta.json").read_text())
    work = BUILD / design_dir.name / "_golden"
    r = check_equivalence(design_dir / "golden.v", design_dir / "golden.v", meta, work, run_eqy=False)
    netlist = json.loads((work / "gold.json").read_text())["modules"][meta["top"]]
    flops = sum(len(c["connections"].get("Q", [])) for c in netlist["cells"].values() if "CLK" in c["connections"])
    text = (design_dir / "golden.v").read_text()
    loc = sum(1 for l in re.sub(r"/\*.*?\*/", "", text, flags=re.S).splitlines()
              if l.strip() and not l.strip().startswith("//"))
    return {"design": design_dir.name, "kind": meta["kind"], "golden_self": r.verdict,
            "loc": loc, "flop_bits": flops}


def provenance() -> dict:
    def out(cmd):
        try:
            return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception:
            return None
    import importlib.metadata as md
    commit = out(["git", "-c", "safe.directory=*", "rev-parse", "--short", "HEAD"])
    if commit and out(["git", "-c", "safe.directory=*", "status", "--porcelain", "--", "mutator", "grader", "tools"]):
        commit += "-dirty"   # generated from uncommitted code
    return {"generator_commit": commit,
            "yosys": out(["yosys", "-V"]), "pyslang": md.version("pyslang"),
            "bmc_budget_s": BMC_BUDGET}


def depth_bin(rec) -> str:
    d = rec["depth"]
    for lo, hi, name in DEPTH_BINS:
        if d["depth_lower"] >= lo and (hi is None or d["depth_upper"] <= hi):
            return name
    return f"{d['depth_lower']}-{d['depth_upper']} (bounds span bins)"


def assign_ids(accepted: list[dict]):
    """Opaque IDs: numbered per design in an order derived from a hash of the buggy text, so an
    ID says nothing about the operator or the line."""
    by_design = defaultdict(list)
    for r in accepted:
        by_design[r["design"]].append(r)
    for design, rs in by_design.items():
        rs.sort(key=lambda r: hashlib.sha256((design + json.dumps(r["edit"], sort_keys=True)).encode()).hexdigest())
        for i, r in enumerate(rs, 1):
            r["id"] = f"{design}_{i:02d}"


def write_outputs(records: list[dict], infos: dict, prov: dict, names: list[str]):
    accepted = [r for r in records if r["outcome"] == "accepted"]
    assign_ids(accepted)
    for name in names:
        shutil.rmtree(BUGS / name, ignore_errors=True)
    manifest = []
    for r in sorted(accepted, key=lambda r: r["id"]):
        design_dir = DESIGNS / r["design"]
        meta = json.loads((design_dir / "meta.json").read_text())
        golden = (design_dir / "golden.v").read_text()
        s, e = r["edit"]["golden_span"]
        buggy = golden[:s] + r["edit"]["replacement"] + golden[e:]
        path = BUGS / r["design"] / f"{r['id']}.v"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(buggy)
        sim = r["simulation"]
        manifest.append({
            "id": r["id"], "design": r["design"], "kind": meta["kind"], "top": meta["top"],
            "file": str(path.relative_to(ROOT)), "candidate": r["cid"],
            "operator": r["operator"], "family": r["family"], "note": r["note"],
            "edit": r["edit"], "localization": r["localization"],
            "formal": {"pdr_cex_step": r["grader"]["pdr_cex_step"], **r["depth"], "depth_bin": depth_bin(r),
                       "failing_outputs": r["grader"]["failing_outputs"], **r["osdd"],
                       "proof_s": r["grader"]["proof_s"]},
            "simulation": {"cex_reproduced": sim["replay_step"] is not None, "replay_step": sim["replay_step"], "replay_output": sim["replay_output"],
                           "replay_shows_x": sim["replay_x"], "random_sim_mismatches": sim["random_sim_mismatches"]},
            "reference_test_detected": r["reference_test_detected"],
            "reference_test": r["reference_test"],
            "design_size": {"loc": infos[r["design"]]["loc"], "flop_bits": infos[r["design"]]["flop_bits"]},
            "golden_sha256": hashlib.sha256(golden.encode()).hexdigest(),
            "buggy_sha256": hashlib.sha256(buggy.encode()).hexdigest(),
            "provenance": prov,
        })
    # Keep entries for designs not regenerated this run.
    old = []
    if (BUGS / "manifest.jsonl").exists() and set(names) != set(infos_all_names()):
        old = [json.loads(l) for l in (BUGS / "manifest.jsonl").read_text().splitlines() if l.strip()]
        old = [x for x in old if x["design"] not in names]
    full = sorted(old + manifest, key=lambda x: x["id"])
    BUGS.mkdir(exist_ok=True)
    (BUGS / "manifest.jsonl").write_text("".join(json.dumps(x) + "\n" for x in full))

    old_c = []
    if (BUGS / "candidates.jsonl").exists() and set(names) != set(infos_all_names()):
        old_c = [json.loads(l) for l in (BUGS / "candidates.jsonl").read_text().splitlines() if l.strip()]
        old_c = [x for x in old_c if x["design"] not in names]
    cands = sorted(old_c + records, key=lambda x: (x["design"], x["cid"]))
    (BUGS / "candidates.jsonl").write_text("".join(json.dumps(x) + "\n" for x in cands))
    write_report(cands, full, prov)


def infos_all_names():
    return sorted(p.name for p in DESIGNS.iterdir() if p.is_dir())


def write_report(cands: list[dict], manifest: list[dict], prov: dict):
    outcomes = ["stillborn", "equivalent", "rejected_formal_pass_sim_fails", "inconclusive", "error",
                "invalid", "rejected_simsynth_disagree", "rejected_cex_not_reproduced", "accepted"]
    short = {"stillborn": "stillborn", "equivalent": "equiv", "rejected_formal_pass_sim_fails": "PASS/sim-fail",
             "inconclusive": "inconcl", "error": "error", "invalid": "invalid",
             "rejected_simsynth_disagree": "sim≠synth", "rejected_cex_not_reproduced": "no replay",
             "accepted": "accepted"}
    by = defaultdict(Counter)
    for c in cands:
        by[c["design"]][c["outcome"]] += 1
    ref_miss = Counter(m["design"] for m in manifest if not m["reference_test_detected"])
    no_replay = Counter(m["design"] for m in manifest if not m["simulation"]["cex_reproduced"])
    L = ["# Bug pool report (Phase 3a)", "",
         "Generated by `make bugs` (mutator/generate.py). Every candidate is one source edit of a golden",
         "design. Acceptance: grader FAIL with a counterexample from reset, the mutant's RTL and",
         "synthesized netlist agree in simulation, and either the reference test fails or the formal",
         "counterexample replays as an output mismatch in Icarus. The reference-test verdict is recorded",
         "as metadata. No eval subset is selected here (Phase 3b).", "",
         f"Tools: {prov['yosys']}; pyslang {prov['pyslang']}; generator commit {prov['generator_commit']}; "
         f"BMC depth budget {prov['bmc_budget_s']} s.", "", "## Funnel per design", "",
         "| Design | Kind | Candidates | " + " | ".join(short[o] for o in outcomes) + " | ref test missed | cex not replayed | equivalent rate |",
         "|" + "---|" * (len(outcomes) + 6)]
    tot = Counter()
    for d in sorted(by):
        c = by[d]
        n = sum(c.values())
        judged = c["equivalent"] + c["accepted"] + c["rejected_simsynth_disagree"] + c["rejected_cex_not_reproduced"]
        rate = f"{100 * c['equivalent'] / judged:.0f}%" if judged else "-"
        kind = json.loads((DESIGNS / d / "meta.json").read_text())["kind"][:4]
        L.append(f"| {d} | {kind} | {n} | "
                 + " | ".join(str(c[o]) for o in outcomes) + f" | {ref_miss[d]} | {no_replay[d]} | {rate} |")
        tot.update(c)
        tot["_ref_miss"] += ref_miss[d]
        tot["_no_replay"] += no_replay[d]
    n = sum(v for k, v in tot.items() if not k.startswith("_"))
    judged = tot["equivalent"] + tot["accepted"] + tot["rejected_simsynth_disagree"] + tot["rejected_cex_not_reproduced"]
    L.append(f"| **total** | | {n} | " + " | ".join(str(tot[o]) for o in outcomes)
             + f" | {tot['_ref_miss']} | {tot['_no_replay']} | {100 * tot['equivalent'] / max(judged, 1):.0f}% |")
    L += ["", "ref test missed = accepted bugs the hidden reference test passes (reference_test_detected =",
          "false); each was kept only because its counterexample replays in simulation. cex not replayed =",
          "accepted bugs the reference test catches whose formal counterexample needs a register start",
          "value that is X in simulation (typically a missing reset); simulation shows them on another trace.",
          "", "Equivalent rate = equivalent / (mutants that compiled and got a PASS/FAIL verdict). Fellner et al.",
          "report 33% on average (range 0-95%) for Verilog mutants.", "",
          "## Accepted bugs by family and depth", "",
          "Depth = minimum counterexample depth from reset (cycles after the reset cycle). When BMC could",
          "not finish within its budget the depth is a [lower, upper] bound; it is binned only when both",
          "bounds fall in one bin.", ""]
    bins = [b[2] for b in DEPTH_BINS]
    fam = defaultdict(Counter)
    for m in manifest:
        fam[m["family"]][m["formal"]["depth_bin"]] += 1
    L += ["| Family | " + " | ".join(bins) + " | other | total |", "|" + "---|" * (len(bins) + 3)]
    for f in sorted(fam):
        other = sum(v for k, v in fam[f].items() if k not in bins)
        L.append(f"| {f} | " + " | ".join(str(fam[f][b]) for b in bins) + f" | {other} | {sum(fam[f].values())} |")
    L += ["", "Comb designs always have depth 0. Timing (clock-edge) and Port mutations are not generated:",
          "the grader cannot compare circuits clocked on different edges, and port changes alter the",
          "interface.", "", "## Accepted bugs by design", "",
          "| Design | Kind | Bugs | " + " | ".join(bins) + " | ref test missed | inexact depth | operators |",
          "|" + "---|" * (len(bins) + 6)]
    per = defaultdict(list)
    for m in manifest:
        per[m["design"]].append(m)
    for d in sorted(per):
        ms = per[d]
        bc = Counter(m["formal"]["depth_bin"] for m in ms)
        ops = Counter(m["operator"] for m in ms)
        L.append(f"| {d} | {ms[0]['kind'][:4]} | {len(ms)} | " + " | ".join(str(bc[b]) for b in bins)
                 + f" | {sum(not m['reference_test_detected'] for m in ms)} | "
                 + f"{sum(not m['formal']['depth_exact'] for m in ms)} | "
                 + ", ".join(f"{k} {v}" for k, v in ops.most_common()) + " |")
    seq = sum(m["kind"] == "sequential" for m in manifest)
    L += ["", f"Pool mix: {seq} sequential / {len(manifest) - seq} combinational bugs "
          f"({100 * seq / max(len(manifest), 1):.0f}% sequential).", "",
          "## Operators", "", "| Operator | Family | Candidates | Accepted | Equivalent | Stillborn |", "|---|---|---|---|---|---|"]
    opc = defaultdict(Counter)
    for c in cands:
        opc[c["operator"]][c["outcome"]] += 1
        opc[c["operator"]]["_n"] += 1
    for op in sorted(opc, key=lambda o: (FAMILY[o], o)):
        c = opc[op]
        L.append(f"| {op} | {FAMILY[op]} | {c['_n']} | {c['accepted']} | {c['equivalent']} | {c['stillborn']} |")
    inv = [c for c in cands if c["outcome"] in ("rejected_formal_pass_sim_fails", "rejected_simsynth_disagree",
                                                 "rejected_cex_not_reproduced", "error", "inconclusive", "invalid")]
    L += ["", "## Rejected for investigation", "",
          "Grader PASS but simulation failed, simulator and synthesis disagree, the counterexample did",
          "not reproduce, or no verdict. None of these are in the benchmark.", ""]
    if inv:
        L += ["| Candidate | Design | Outcome | Operator | Edit | Reason |", "|---|---|---|---|---|---|"]
        for c in inv:
            L.append(f"| {c['cid']} | {c['design']} | {c['outcome']} | {c['operator']} | {c['note'][:60].replace('|', '/')} "
                     f"| {c.get('reason', '')[:110].replace('|', '/')} |")
    else:
        L.append("None.")
    (BUGS / "REPORT.md").write_text("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("designs", nargs="*")
    ap.add_argument("--jobs", type=int, default=6)
    args = ap.parse_args()
    names = args.designs or infos_all_names()

    with ProcessPoolExecutor(args.jobs) as ex:
        infos = {i["design"]: i for i in ex.map(design_info, [DESIGNS / n for n in names])}
    for n, i in infos.items():
        if i["golden_self"] != "PASS":
            sys.exit(f"{n}: grader does not PASS golden vs itself ({i['golden_self']}); run make corpus-check")

    tasks = []
    for n in names:
        golden = (DESIGNS / n / "golden.v").read_text()
        for i, m in enumerate(enumerate_mutations(Design(golden), n), 1):
            tasks.append((str(DESIGNS / n), f"{n}-c{i:04d}", {**m.__dict__, "scope": list(m.scope)}))
    print(f"{len(tasks)} candidates from {len(names)} designs, {args.jobs} workers", flush=True)

    records, started = [], time.monotonic()
    with ProcessPoolExecutor(args.jobs) as ex:
        futures = [ex.submit(process, t) for t in tasks]
        for k, f in enumerate(as_completed(futures), 1):
            records.append(f.result())
            if k % 50 == 0 or k == len(tasks):
                c = Counter(r["outcome"] for r in records)
                print(f"[{k}/{len(tasks)} {time.monotonic() - started:5.0f}s] " +
                      ", ".join(f"{o} {v}" for o, v in c.most_common()), flush=True)

    write_outputs(records, infos, provenance(), names)
    c = Counter(r["outcome"] for r in records)
    print(f"\naccepted {c['accepted']} of {len(records)} candidates; see bugs/REPORT.md")


if __name__ == "__main__":
    main()
