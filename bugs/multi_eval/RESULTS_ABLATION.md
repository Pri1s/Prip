# Agent vs No-sim agent vs Baseline vs Best-of-k: eval-haiku, eval-haiku-bestof, eval-haiku-nosim

Models: agent `anthropic/claude-haiku-5.5`, no-sim agent `anthropic/claude-haiku-5.5`, baseline `anthropic/claude-haiku-5.5`, best-of-k `anthropic/claude-haiku-5.5`. 180 bugs.

| | Agent | No-sim agent | Baseline | Best-of-k |
|---|---|---|---|---|
| Repair PASS | 344/360 (96%) | 256/360 (71%) | 234/360 (65%) | 297/360 (82%) |
| Exact line (any bug's line) | 355/360 (99%) | 357/360 (99%) | 358/360 (99%) | 357/360 (99%) |
| API/format errors | 0 | 0 | 0 | 0 |
| Cost | $1.79 ($0.0050/run) | $0.90 ($0.0025/run) | $0.69 ($0.0019/run) | $2.06 ($0.0057/run) |
| Cost per run vs agent | 1.00x | 0.50x | 0.39x | 1.15x |

**Paired runs, agent vs no-sim agent** (bug, repeat; 360 pairs):

| | No-sim agent PASS | No-sim agent FAIL |
|---|---|---|
| **Agent PASS** | 248 | 96 |
| **Agent FAIL** | 8 | 8 |

McNemar exact, Agent vs No-sim agent (runs): 96 vs 8 discordant, p = 2.8e-20
McNemar exact, Agent vs No-sim agent (per bug, majority over repeats): 60 vs 3 discordant, p = 9e-15

**Paired runs, agent vs baseline** (bug, repeat; 360 pairs):

| | Baseline PASS | Baseline FAIL |
|---|---|---|
| **Agent PASS** | 229 | 115 |
| **Agent FAIL** | 5 | 11 |

McNemar exact, Agent vs Baseline (runs): 115 vs 5 discordant, p = 3e-28
McNemar exact, Agent vs Baseline (per bug, majority over repeats): 75 vs 3 discordant, p = 5.2e-19

**Paired runs, agent vs best-of-k** (bug, repeat; 360 pairs):

| | Best-of-k PASS | Best-of-k FAIL |
|---|---|---|
| **Agent PASS** | 289 | 55 |
| **Agent FAIL** | 8 | 8 |

McNemar exact, Agent vs Best-of-k (runs): 55 vs 8 discordant, p = 9.8e-10
McNemar exact, Agent vs Best-of-k (per bug, majority over repeats): 41 vs 5 discordant, p = 4.4e-08

McNemar exact, Best-of-k vs Baseline (runs): 77 vs 14 discordant, p = 1e-11
McNemar exact, Best-of-k vs Baseline (per bug, majority over repeats): 42 vs 6 discordant, p = 1e-07

**Best-of-k**:

- k = [3], candidate temperature = [1.0], selector `anthropic/claude-haiku-5.5` at temperature 0.0
- distinct candidates per run: mean 1.68
- selector called in 194/360 runs (0 fell back to candidate 1); selector cost $0.1703 of $2.0617
- any candidate passed (perfect-selector diagnostic, not a score): 298/360 (83%)

**Metric A: test exposure capability** (each run's final tests, executed or not, replayed in the sandbox; a test function must fail on buggy and pass on golden):

| | Agent | Baseline | Best-of-k |
|---|---|---|---|
| Runs replayed | 360/360 | 360/360 | 360/360 |
| Left a test | 358/360 (99%) | 358/360 (99%) | 358/360 (99%) |
| A test fails on buggy | 352/360 (98%) | 354/360 (98%) | 354/360 (98%) |
| **Exposes the bug** | 351/360 (98%) | 320/360 (89%) | 334/360 (93%) |

**Metric B: executed exposure (agent only; not applicable to arms that never run a test):**

- a test failed on the buggy RTL during the run: 317/360 (88%)
- ... and failed again in the replay: 317/360 (88%)
- ... and that test passes on golden (validated): 295/360 (82%)
- failing tests that also fail on golden only (false alarm): 22/360 (6%)

**Agent tool use**:

- ran at least one cocotb test: 358/360 (99%)
- had a test fail on the original buggy file: 316/360 (88%)
- tool calls per run: mean 8.0
- stop reasons: {'submitted': 360}
**Notes**

- No-sim agent = the same agent loop, model, budgets and eval set without `run_cocotb` (the tool is
  not registered and the server refuses it); the prompt changes only where it needs simulation
  (agent/prompts.py AGENT_GUIDE_NOSIM, toolserver INSTRUCTIONS_NOSIM). Frozen in 874495c before the
  run. It used 3.5 tool calls per run on average, wrote no test files and submitted in all 360 runs.
- Removing simulation drops repair from 96% to 71% (agent-only 96 vs no-sim-only 8 pairs,
  p = 2.8e-20). The no-sim agent is only modestly above single-shot (55 vs 33, p = 0.025) and below
  best-of-3. This is a simulation-*tool* ablation: the prompt difference is part of the treatment.
- Metric A (final tests): the agent's tests were run and revised during the run, the baselines'
  never ran, so A compares the tests each approach delivers, not blind test-writing ability.
- 2 repeats per bug; Haiku 5.5 only; three-bug variants only; localization saturated (any of the
  three lines counts).
