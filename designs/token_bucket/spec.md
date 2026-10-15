# token_bucket

A rate limiter. It holds up to 3 tokens. Each granted request spends one token,
and the bucket earns one token back every 5 clock cycles.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | Clock; state changes on its rising edge |
| `rst` | in | 1 | Synchronous reset, active high |
| `req` | in | 1 | A request is waiting this cycle |
| `grant` | out | 1 | The request is accepted this cycle |
| `level` | out | 2 | Tokens currently in the bucket (0–3) |

## Behavior

- `grant` reacts to the current `req` within the same cycle: it is high exactly
  when `req` is high and `level` is not zero.
- A refill timer counts clock cycles. It runs all the time, including while the
  bucket is full and while requests are being granted. Every 5th rising edge
  after reset is a refill edge (the 5th, 10th, 15th, …).
- On each rising edge, starting from the current `level`:
  1. take one token away if `grant` is high this cycle;
  2. then, if this is a refill edge and the bucket holds fewer than 3 tokens,
     add one token.
  The result is the new `level`. A refill that arrives while the bucket is
  already full is lost.
- A rising edge with `rst` high fills the bucket to 3 tokens and restarts the
  refill timer, so the next refill edge is the 5th edge after reset is released.
