# Agent vs baseline: eval-haiku

Models: agent `anthropic/claude-haiku-5.5`, baseline `anthropic/claude-haiku-5.5`. 180 bugs, 360 paired runs.

| | Agent | Baseline |
|---|---|---|
| Repair PASS | 344/360 (96%) | 234/360 (65%) |
| Exact line (any bug's line) | 355/360 (99%) | 358/360 (99%) |
| API/format errors | 0 | 0 |
| Cost | $1.79 ($0.0050/run) | $0.69 ($0.0019/run) |

**Paired runs** (bug, repeat):

| | Baseline PASS | Baseline FAIL |
|---|---|---|
| **Agent PASS** | 229 | 115 |
| **Agent FAIL** | 5 | 11 |

McNemar exact (runs): 115 vs 5 discordant, p = 3e-28
McNemar exact (per bug, majority over repeats): 75 vs 3 discordant, p = 5.2e-19

**Agent tool use**:

- ran at least one cocotb test: 358/360 (99%)
- had a test fail on the original buggy file: 316/360 (88%)
- tool calls per run: mean 8.0
- stop reasons: {'submitted': 360}
**Notes**

- 2 repeats per bug, not the planned 3: the key's $5 credit limit ran out ($0.59 left). The per-bug
  row counts a bug as passed only if both repeats passed.
- "Test failed on the original" is not yet *exposure*: Phase 6b replays those tests on golden in a
  sandbox and adds the validity and recognition checks.
- Not cost-matched: the agent spends ~2.6x the baseline per bug. A best-of-3 baseline costs about
  the same as one agent run and is the obvious next control.
- Exact localization is saturated for three-bug variants (any of 3 lines counts); a stricter
  multi-bug metric belongs in Phase 6b.
- Sonnet 5.5 solves these variants single-shot (probe: 30/30), so this result is about Haiku 5.5.
