# Prip — RTL Debug Agent

An LLM agent that debugs Verilog. Given buggy RTL and a plain-language spec (and no
testbench), it writes its own cocotb tests, simulates, localizes the buggy line, and
patches it. A fix only counts if a formal equivalence proof shows the patched design
behaves exactly like the original from reset.

The agent is measured on a self-built benchmark of formally filtered mutants, against a
single-shot baseline, on detection rate, localization accuracy, verified fix rate, and cost
per bug.

Everything uses free, open-source EDA tools and runs on a laptop inside Docker.

## Status

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Docker toolchain (OSS CAD Suite + cocotb) with FIFO smoke test | Done |
| 2 | Design corpus: 15 Verilog-2005 designs with specs, reference tests, known-bad controls | Done |
| 4a | Formal equivalence grader (whole-design miter, PDR) + validation set | Done |
| 3a | Bug pool: source mutator, filtered by the grader and checked in simulation | Done |
| 3b | Choose the evaluation subset from the pool | Next |
| 4b | Grading flow: hidden reference testbench + bug-line localization check | Planned |
| 5 | MCP tool server: `read_file`, `write_file`, `lint`, `run_cocotb`, `submit_patch` | Planned |
| 6 | Agent, single-shot baseline, parallel eval runner | Planned |
| 7 | Waveform summarizer (Python prototype, then C++) | Planned |

## Quick start

Requires Docker. The image builds for amd64 and arm64 (tested on Apple Silicon).

```bash
make image            # build the toolchain image (OSS CAD Suite 2026-10-01, Python 3.11, cocotb 2.0.1)
make smoke            # Phase 1 check: FIFO cocotb test + grader PASS/FAIL controls
make corpus-check     # every design lints, passes its reference test, self-proves, rejects its controls
make grader-validate  # labeled buggy/equivalent variants must all get the expected verdict
make bugs             # Phase 3a: regenerate the bug pool in bugs/ (about 20 min)
make bugs-check       # re-verify every committed bug against the current golden designs
make mutator-test     # unit tests for the mutation operators
make shell            # interactive shell in the container, repo mounted at /work
```

Limit checks to a subset with `make corpus-check DESIGNS="op_unit token_bucket"` or
`make grader-validate SUITES="fifo seq_divider"`.

## How grading works

`grader/equiv.py` decides whether a patched design is externally equivalent to the golden one:

1. Golden and patch are flattened and placed side by side in a miter that drives both with the
   same inputs, applies reset in cycle 0, and asserts every output matches from then on.
2. SBY's `abc pdr` engine tries to prove the assertions (default 60 s; a design's `meta.json`
   can raise it with `prove_timeout`). PDR finds inductive invariants on its own, so it can
   prove designs whose internal state is renamed or re-encoded, where k-induction gets stuck.
3. A cover check confirms reset and every validity condition are reachable, so a proof can't
   pass vacuously.
4. Outputs that are only meaningful sometimes (e.g. a divider's quotient before `done`) have a
   benchmark-defined `valid_when` rule. The rule reads the **golden** design's signals, so a
   buggy patch can't hide its own outputs.

| Verdict | Meaning |
|---------|---------|
| PASS | Equivalence proved, and the proof is non-vacuous |
| FAIL | Counterexample from reset, or the patch is invalid (doesn't elaborate, wrong ports, a clock or clock edge golden doesn't use, formal cells, `` `include ``/`` `ifdef ``) |
| INCONCLUSIVE | Timeout or unknown; earns no credit, reported separately from FAIL |
| ERROR | The grader itself broke; rerun, don't score |

EQY (`sby` strategy) also runs as a diagnostic only. It never changes the verdict; its
partitioned check is stricter than reset-reachable equivalence and wrongly fails many correct
rewrites, so disagreements are logged for analysis.

Grade a file by hand inside the container:

```bash
python -m grader.equiv --design designs/token_bucket --gate patch.v --work build/grade/x
```

## Design corpus

15 designs (10 sequential, 5 combinational). 12 are derived from
[RTLLM](https://github.com/hkust-zhiyao/RTLLM) and changed in behavior, not just renamed, to
reduce training-data contamination; 3 are original. All sequential designs use a synchronous
active-high reset.

| Combinational | Sequential |
|---------------|------------|
| `bcd_sum`, `mag_compare`, `op_unit`, `rotate_shift`, `secded_decode`* | `clock_counter`, `pack_8to16`, `pattern_watch`, `rr_arbiter`*, `sample_accum`, `seq_divider`, `signal_light`, `stack_buffer`, `token_bucket`*, `updown_count` |

\* original design

Each `designs/<name>/` holds:

| File | Visible to agent | Purpose |
|------|------------------|---------|
| `spec.md` | Yes | Plain-language behavior and ports |
| `golden.v` | No | Reference RTL |
| `ref_test.py` | No | cocotb test with a Python model, used for grading |
| `meta.json` | No | Top, clock/reset, origin + license, disguise changes, `compare` masks, timeout |
| `controls/*.v` | No | Hand-written buggy variants the grader and reference test must both reject |

## Bug pool (Phase 3a)

`make bugs` mutates each golden design one edit at a time (20 operators in three VeriBugBench
families: Expression, Bit-vector & access, Assignment) and runs every mutant through the same gates:

1. **Lint**: compiles under `iverilog -g2005`, synthesizes, no latches, still combinational/sequential.
2. **Grader**: FAIL with a counterexample from reset continues; PASS means an equivalent mutant.
3. **Depth**: BMC from reset finds the minimum counterexample depth (PDR's trace was longer on
   22 bugs). If BMC can't finish in 60 s, the depth is stored as `[lower, upper]` bounds.
4. **Simulation**: the counterexample is replayed in Icarus on golden vs mutant RTL, and the
   mutant's RTL simulation must agree with simulation of its own synthesized netlist.
5. **Reference test**: run and recorded as `reference_test_detected`; it is metadata, not a gate.

| Grader | Simulation | Outcome |
|--------|------------|---------|
| FAIL | reference test fails | accepted |
| FAIL | reference test passes, counterexample replays as an output mismatch | accepted, `reference_test_detected = false` |
| FAIL | RTL and netlist disagree, or simulation never settles | rejected |
| PASS | reference test or simulation fails | rejected, listed for investigation |
| INCONCLUSIVE / ERROR | | rejected, counted in the report |

Clock-edge (`posedge`↔`negedge`) and port mutations are not generated.

Current pool: 1,257 candidates → **1,056 accepted** (662 sequential, 394 combinational), 119
equivalent (10%), 63 stillborn, 19 rejected for simulation/synthesis disagreement or a grader
error. The reference test misses 2 accepted bugs. See [bugs/REPORT.md](bugs/REPORT.md) for the
per-design funnel and family × depth counts. Phase 3b chooses the evaluation subset.

Per bug, `bugs/manifest.jsonl` (answer key, never shown to the agent) records the operator,
family, exact edit, localization lines (for deletions: the line where code is missing and its
enclosing block), minimum depth, OSDD, failing outputs, simulation and reference-test results,
design size, and hashes. Bug IDs are opaque (`token_bucket_07`); the agent gets only the buggy
file (as `<top>.v`) and `spec.md`. `make bugs-check` re-verifies every bug against the current
golden designs.

## Repository layout

```
docker/        Dockerfile and vvp wrapper (keeps pinned cocotb ahead of the suite's bundled copy)
designs/       benchmark corpus (see above); THIRD_PARTY.md has the RTLLM license
grader/        equiv.py (formal grader), ref_runner.py (reference test runner), validation/ suites
tools/         corpus_check.py, validate_grader.py, bugs_check.py
smoke/         FIFO, two hand-edited bad FIFOs, cocotb test, run.sh
docs/research/ notes on RTL bug taxonomies, bug depth vs difficulty, and contamination
mutator/       mutation operators (pyslang), simulation checks, bug-pool generator
bugs/          generated bug pool: <design>/<id>.v, manifest.jsonl (answer key), candidates.jsonl, REPORT.md
agent/         placeholder for Phase 6
```

## Isolation (planned for Phases 5–6)

The answer key (golden RTL, reference tests, bug manifest) exists only in the grader
environment. The agent works on a fresh copy of the buggy RTL and spec, and any tool that
runs agent-written code does so in a no-network container. Each run ends with one
`submit_patch`; grading happens afterwards.

## License

Designs derived from RTLLM are used under the MIT License; see
[designs/THIRD_PARTY.md](designs/THIRD_PARTY.md).
