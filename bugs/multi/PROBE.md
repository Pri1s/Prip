# Phase 6c difficulty probe

Single-shot baseline only (the agent was not run), dev designs only. Rule fixed in advance: the cheapest cell with baseline repair 20%-60% becomes the benchmark setting; the new eval set is then generated fresh (new seed, bugs never used here).

| Model | Bugs | Repair PASS | Exact line | Block | Cost/run | In window |
|---|---|---|---|---|---|---|
| Sonnet 5.5 | single (dev 30) | 30/30 (100%) | 29/30 | 30/30 | $0.0170 | no |
| Sonnet 5.5 | three bugs (probe 30) | 30/30 (100%) | 30/30 | 30/30 | $0.0225 | no |
| Haiku 5.5 | single (dev 30) | 30/30 (100%) | 30/30 | 30/30 | $0.0012 | no |
| Haiku 5.5 | three bugs (probe 30) | 18/30 (60%) | 30/30 | 30/30 | $0.0018 | yes |

**Pick: Haiku 5.5, three bugs (probe 30)** (cheapest cell in the window).
