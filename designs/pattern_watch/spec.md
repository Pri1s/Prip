# pattern_watch

Watches a serial bit stream and raises a flag each time the last four bits
received were `1`, `1`, `0`, `1` (oldest first).

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | Clock; everything happens on its rising edge |
| `rst` | in | 1 | Synchronous reset, active high |
| `din` | in | 1 | Serial input, one bit sampled per rising edge |
| `seen` | out | 1 | High while the four most recent samples are `1101` |

## Behavior

- One bit of `din` is taken on every rising edge where `rst` is low.
- After the edge that takes the fourth bit of a `1101` run, `seen` is high for
  the following clock cycle. It is driven only by stored state, not directly by
  `din`.
- Matches may overlap: the last `1` of one match can be the first `1` of the
  next. For example, the input `1101101` produces two matches.
- A rising edge with `rst` high forgets all earlier input. Only bits taken after
  reset is released count toward a match, and `seen` is low after reset.
