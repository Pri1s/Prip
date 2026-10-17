# Agent vs Baseline vs Best-of-k: eval-haiku, eval-haiku-bestof

Models: agent `anthropic/claude-haiku-5.5`, baseline `anthropic/claude-haiku-5.5`, best-of-k `anthropic/claude-haiku-5.5`. 180 bugs.

| | Agent | Baseline | Best-of-k |
|---|---|---|---|
| Repair PASS | 344/360 (96%) | 234/360 (65%) | 297/360 (82%) |
| Exact line (any bug's line) | 355/360 (99%) | 358/360 (99%) | 357/360 (99%) |
| API/format errors | 0 | 0 | 0 |
| Cost | $1.79 ($0.0050/run) | $0.69 ($0.0019/run) | $2.06 ($0.0057/run) |
| Cost per run vs agent | 1.00x | 0.39x | 1.15x |

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

**Agent tool use**:

- ran at least one cocotb test: 358/360 (99%)
- had a test fail on the original buggy file: 316/360 (88%)
- tool calls per run: mean 8.0
- stop reasons: {'submitted': 360}
**Notes**

- Best-of-k is cost-matched by a rule fixed on dev before this run (bugs/multi/BESTOF_TUNE.md):
  k = 3 at T = 1.0 cost $0.0055/run on dev (1.11x agent). On the eval set it cost $0.0057/run
  (1.15x, the cap), so it spent slightly more than the agent: the comparison leans toward the baseline.
- The selector is not the bottleneck: it picked a passing candidate in 297 of the 298 runs where
  one existed. The candidates are: 1.68 distinct per run at T = 1.0, and 62/360 runs had no passing one.
- 2 repeats per bug, paired with runs/eval-haiku's agent runs (r1, r2). Same caveats as RESULTS.md
  (Haiku 5.5 only; exact localization saturated for three-bug variants; exposure not yet replayed).
