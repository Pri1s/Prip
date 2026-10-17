# Best-of-k baseline tuning (dev, Haiku 5.5, three-bug probe set)

Agent eval cost per run $0.0050; cap = 1.15x = $0.0057. Rule: see tools/bestof_tune.py.

| k | T | Selected repair | Any candidate (diagnostic) | Distinct cands | Selector calls | Cost/run | vs agent |
|---|---|---|---|---|---|---|---|
| 3 | 0.2 | 22/30 | 22/30 | 1.57 | 14 (0 fallback) | $0.0054 | 1.09x |
| 3 | 0.7 | 24/30 | 24/30 | 1.83 | 22 (0 fallback) | $0.0054 | 1.09x |
| 3 | 1.0 | 25/30 | 25/30 | 1.87 | 22 (0 fallback) | $0.0055 | 1.11x |

**Decision:** T = 1.0, k = 3 (k=3 cost $0.0055 <= cap $0.0057)
