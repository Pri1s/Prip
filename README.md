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
| 3b | Frozen 180-bug eval set + 30-bug dev set, stratified by kind and depth | Done |
| 4b | Grading flow: hidden reference testbench + bug-line localization check | Done |
| 5 | MCP tool server: `read_file`, `write_file`, `lint`, `run_cocotb`, `submit_patch`, sandboxed | Done |
| 6a | Agent loop (OpenRouter), single-shot baseline, parallel eval runner with cost tracking | Done (live pilot not yet run) |
| 6c | Difficulty probe: the dev pilot saturated (both arms 30/30), so model × single/three-bug cells were measured for the baseline only | Done: Haiku 5.5 + three bugs = 60% |
| 6c eval | Fresh 180 three-bug variants, agent vs baseline on Haiku 5.5, 2 repeats | Done: repair 96% vs 65%, McNemar p ≈ 3e-28 ([results](bugs/multi_eval/RESULTS.md)) |
| 6b | Detection scoring (exposure replay, recognition judge), McNemar report | Planned |
| 7 | Waveform summarizer (Python prototype, then C++) | Planned |

## Quick start

Requires Docker. The image builds for amd64 and arm64 (tested on Apple Silicon). The tool server
also needs Python 3.11+ on the host (`make host-venv`).

```bash
make image            # build the toolchain image (OSS CAD Suite 2026-10-01, Python 3.11, cocotb 2.0.1)
make smoke            # Phase 1 check: FIFO cocotb test + grader PASS/FAIL controls
make corpus-check     # every design lints, passes its reference test, self-proves, rejects its controls
make grader-validate  # labeled buggy/equivalent variants must all get the expected verdict
make bugs             # Phase 3a: regenerate the bug pool in bugs/ (about 20 min)
make bugs-check       # re-verify every committed bug against the current golden designs
make subset           # Phase 3b: select the eval/dev sets (refuses to replace a frozen eval set without FORCE=1)
make subset-check     # re-verify the eval/dev sets: quotas, caps, disjoint, reproducible
make mutator-test     # unit tests for the mutation operators
make grader-test      # unit tests: SBY log reading, verdict combination, localization scoring, patch rules
make grade-check      # Phase 4b: full grading flow on every eval/dev bug, correct rewrites, sim-broken patches
make host-venv        # host Python env for the tool server (mcp 2.3.0, pytest)
make tools-test       # Phase 5: tool-server tests against a real sandbox (escape attempts, timeouts, budget)
make tools-check      # Phase 5: scripted client over MCP on the 30 dev bugs, then graded (about 4 min)
make agent-test       # Phase 6a: agent loop, baseline, OpenRouter client against a fake API (no cost)
make bugs-multi       # Phase 6c: three-bug variants of the pool -> bugs/multi/ (container)
make bugs-multi-eval  # Phase 6c: the fresh 180-variant three-bug eval set -> bugs/multi_eval/ (container)
make eval-haiku       # Phase 6c: agent vs baseline on Haiku 5.5 over that set (paid, about $1.25 per repeat)
make probe            # Phase 6c: baseline on the probe cells, table in bugs/multi/PROBE.md (paid, about $0.60)
make agent-pilot      # Phase 6a: both arms on the 30 dev bugs, graded, cost projected (needs OPENROUTER_API_KEY; spends money)
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
| FAIL | Counterexample from reset (also when SBY then fails to write the trace, e.g. a patch reading an out-of-range bit), or the patch is invalid (doesn't elaborate, wrong ports, a clock or clock edge golden doesn't use, formal cells, `` `include ``/`` `ifdef ``, file-access system tasks such as `$fopen`/`$readmemh`) |
| INCONCLUSIVE | Timeout or unknown; earns no credit, reported separately from FAIL |
| ERROR | The grader itself broke (including a crash inside PDR); rerun, don't score |

EQY (`sby` strategy) also runs as a diagnostic only. It never changes the verdict; its
partitioned check is stricter than reset-reachable equivalence and wrongly fails many correct
rewrites, so disagreements are logged for analysis.

Grade a file by hand inside the container:

```bash
python -m grader.equiv --design designs/token_bucket --gate patch.v --work build/grade/x
```

## Scoring a submission (Phase 4b)

`grader/grade.py` scores one run for one bug. Repair and localization are scored **separately**:
an agent can find the right line and still fail to fix it, or fix the bug without pinpointing it.

**Repair** needs both checks to pass. The hidden reference test (`ref_test.py`) runs on the patch
alongside the formal proof, because a patch can be formally equivalent and still behave differently
in an event-driven simulator (e.g. token_bucket's `<=` → `=` change, or an `always @*` block that
never settles).

| Formal (PDR) | Reference test | Repair verdict |
|--------------|----------------|----------------|
| PASS | passes | **PASS** |
| PASS | fails, crashes, or times out (60 s) | FAIL |
| FAIL | any | FAIL |
| INCONCLUSIVE / ERROR | fails | FAIL |
| INCONCLUSIVE / ERROR | passes | INCONCLUSIVE / ERROR (no credit) |

Both raw results are kept in `grade.json`. A patch rejected by the source rules is never simulated.

**Localization**: the agent claims one line, numbered as in the **original buggy file** it was
given (not its edited copy).

| Field | Counts when the claimed line is |
|-------|---------------------------------|
| `exact` (headline metric) | the edited line; for a deletion, the line just before or just after the missing code (blank lines and comments skipped) |
| `block` (reported separately) | inside the enclosing block from the manifest; every exact hit is also a block hit |

No claimed line, or one outside the file, scores false on both.

```bash
python -m grader.grade --bug token_bucket_07 --patch patch.v --line 24 --work build/grade/x
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
error (the 2 grader errors were out-of-range bit reads, which the grader now scores as FAIL; they
stay out of the pool because they have no counterexample trace to measure). The reference test misses 2 accepted bugs. See [bugs/REPORT.md](bugs/REPORT.md) for the
per-design funnel and family × depth counts.

Per bug, `bugs/manifest.jsonl` (answer key, never shown to the agent) records the operator,
family, exact edit, localization lines (for deletions: the line where code is missing and its
enclosing block), minimum depth, OSDD, failing outputs, simulation and reference-test results,
design size, and hashes. Bug IDs are opaque (`token_bucket_07`); the agent gets only the buggy
file (as `<top>.v`) and `spec.md`. `make bugs-check` re-verifies every bug against the current
golden designs.

## Evaluation subset (Phase 3b)

`make subset` picks a frozen **eval set of 180 bugs** and a disjoint **dev set of 30** (for
building and tuning prompts; reported results come only from the eval set). Strata follow the
research question, bug depth: 54 combinational (depth 0) and 42 each of sequential depth 1–2,
3–5 and 6+ (70% sequential). Within a stratum the quota is spread over designs as evenly as their
bug counts allow (so `seq_divider`, with 126 of the 274 deep bugs, can't dominate), and
`wrong_signal` is at most a third of each design's picks. Families are reported, not given
quotas. Selection is seeded and reproducible; `make subset-check` verifies it. See
[bugs/SUBSET.md](bugs/SUBSET.md), which also records the Phase 6 protocol (3 runs per bug,
McNemar's test for agent vs baseline).

## Repository layout

```
docker/        Dockerfile and vvp wrapper (keeps pinned cocotb ahead of the suite's bundled copy)
designs/       benchmark corpus (see above); THIRD_PARTY.md has the RTLLM license
grader/        grade.py (scores a submission), equiv.py (formal grader), ref_runner.py (reference test runner), validation/ suites
toolserver/    MCP tool server (server.py), workspace.py, sandbox.py, box_runner.py (runs inside the sandbox)
tools/         corpus_check.py, validate_grader.py, bugs_check.py, subset_check.py, grade_check.py,
               grade_runs.py (grades tool-server runs), tools_check.py
smoke/         FIFO, two hand-edited bad FIFOs, cocotb test, run.sh
docs/research/ notes on RTL bug taxonomies, bug depth vs difficulty, and contamination
mutator/       mutation operators (pyslang), simulation checks, bug-pool generator
bugs/          generated bug pool: <design>/<id>.v, manifest.jsonl (answer key), candidates.jsonl, REPORT.md;
               multi/ = Phase 6c three-bug variants (manifest.jsonl, probe_set.json, PROBE.md)
agent/         run_agent.py (agent loop), baseline.py, eval.py (parallel runner), llm.py (OpenRouter), prompts.py, config.json
```

## Tool server and isolation (Phase 5)

The agent only ever acts through five MCP tools, served by `toolserver/server.py` (one process
per run, MCP over stdio). The server runs **on the host, outside the sandbox**: it holds the state
the agent must not be able to change (the one submission, the budget, the trace). Agent-controlled
code (its RTL and its Python tests) runs in a per-run **sandbox container**.

```
host:      agent loop (Phase 6) ⇄ MCP stdio ⇄ tool server ── runs/<run>/{run.json, trace.jsonl, history/, submission/}
                                                    │ docker exec (lint, run_cocotb)
sandbox:   --network none, read-only root fs, workspace mounted read-only at /ws, /tmp scratch (512 MB),
           no capabilities, user nobody, 2 GB / 256 processes, 60 s per call, all processes killed after each call
grader:    container with the repo (answer key), run after the agent is done: tools/grade_runs.py
```

| Tool | Does |
|------|------|
| `read_file(path, start_line?, end_line?)` | Numbered lines of `<top>.v`, `spec.md`, `original/<top>.v` or `tests/<name>.py` |
| `write_file(path, content)` | Replaces `<top>.v` or `tests/<name>.py`; nothing else is writable |
| `lint()` | `iverilog -g2005 -Wall`, Yosys elaboration, and the grader's patch rules (`` `include ``/`` `ifdef ``, file I/O tasks, formal-only constructs) |
| `run_cocotb(test_file, target?, testcase?)` | One of the agent's tests on the working copy (`working`) or the buggy file as given (`original`): per-test PASS/FAIL with the assertion message, end of the log (8,000 characters), or TIMEOUT |
| `submit_patch(line, explanation)` | Submits `<top>.v` and the claimed line (numbered as in `original/<top>.v`); once; the run ends and every tool refuses afterwards |

- **Workspace**: `<top>.v` (editable), `spec.md`, `original/<top>.v` (read-only), `tests/`. No golden
  RTL, reference test, manifest, `meta.json` or bug ID.
- **Only the server writes the workspace.** The sandbox mounts it read-only, so agent code can't
  plant files, symlinks or fill the host disk. The server still refuses symlinks, FIFOs and any path
  outside the fixed layout.
- **Budget**: 40 tool calls and 15 minutes per run (`--max-calls`, `--max-seconds`); running out
  ends the run without a submission, which counts as a failure.
- **Trace**: every call goes to `trace.jsonl` (file contents as hashes). Every `run_cocotb` saves
  the test files it ran, the RTL it ran on, and the per-test results in `history/<n>/`, with one
  recorded `RANDOM_SEED` per run, so Phase 6 can replay the agent's tests offline.
- **`run_cocotb` results are feedback, not evidence.** The agent's test can print anything, so its
  result is never scored. Phase 6 measures **detection** by replaying the agent's tests offline: a
  test counts only if it fails on the buggy RTL and passes on golden. That replay runs agent Python
  next to the answer key, so it must run in the same kind of sandbox with only a copy of `golden.v`.

```bash
.venv/bin/python -m toolserver.server --bug token_bucket_07 --runs-dir runs   # one run, MCP on stdio
docker run --rm -v "$PWD":/work -w /work rtl-debug-agent:dev python tools/grade_runs.py grade runs
```

## Agent and baseline (Phase 6a)

Both arms use the same model, temperature (0.2) and inputs: the spec plus the buggy file numbered
as `read_file` numbers it (`agent/prompts.py`). The only difference is the tool loop.

- **Agent** (`agent/run_agent.py`): starts the tool server as an MCP stdio subprocess, offers its
  five tools to the model as function tools, and feeds results back until the server says the run
  is over (submitted / budget exhausted) or a loop cap hits: 60 LLM turns, 1.5 M tokens, 15 min,
  two replies in a row without a tool call, or an API error the one retry didn't fix. The model's
  text goes to `messages.jsonl`, so Phase 6b can judge whether it *recognized* the bug.
- **Baseline** (`agent/baseline.py`): one call, no tools, JSON reply `{line, explanation,
  patched_file, test?}`, written in the tool server's run layout so `tools/grade_runs.py` grades
  both arms the same way. A bad reply is retried once, then the run has no submission.
- **Runner** (`agent/eval.py`): `<out>/<arm>-<bug>-r<k>/` per run, N in parallel, resumable;
  grades in the container, then writes `summary.json` with outcomes, tokens, cost and the cost
  projected for the full eval (180 bugs × 3 runs per arm).
- **API key**: `OPENROUTER_API_KEY` (from `.env` or the environment) stays on the host in the request header. It never reaches the
  tool server, the sandbox or any run file (`make agent-test` checks this). `.env` is gitignored, excluded from the
  Docker build context, mode 600, and hidden behind an empty file in every container that mounts the repo
  (`repo_mount` in `toolserver/sandbox.py`, `MOUNT` in the Makefile).
- **Cost**: Anthropic models get prompt-cache breakpoints (system prompt + newest message), so
  each turn rereads the conversation at the cached price. Models live in `agent/config.json`.

Detection is scored in Phase 6b: *exposure* (an executed test fails on buggy and passes on golden
in a sandboxed replay), *validity* (it checks spec-defined, unmasked behavior) and *recognition*
(the agent then names the violating behavior; judged from `messages.jsonl` by a fixed-rubric LLM
judge from a different model family, blind to the repair verdict, checked against hand labels).
A run that ends without a submission fails repair and localization but can still earn exposure and
recognition.

Put the key in `.env` at the repo root (gitignored; template in `.env.example`) or export it.

```bash
.venv/bin/python -m agent.run_agent --bug token_bucket_07 --runs-dir runs   # one agent run
.venv/bin/python -m agent.eval --set dev --limit 5 --out runs/try          # small paid trial
```

## License

Designs derived from RTLLM are used under the MIT License; see
[designs/THIRD_PARTY.md](designs/THIRD_PARTY.md).
