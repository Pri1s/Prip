# rr_arbiter

Shares one resource among four requesters, taking turns in round-robin order.
A requester can keep the resource for a while, but not forever if others are
waiting.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | Clock; state changes on its rising edge |
| `rst` | in | 1 | Synchronous reset, active high |
| `req` | in | 4 | `req[i]` high: requester `i` wants the resource |
| `grant` | out | 4 | `grant[i]` high: requester `i` has the resource this cycle |

## Behavior

`grant` is registered: it changes only on rising edges, so it answers the
`req` values seen at the previous edge. At most one bit of `grant` is high.

After a rising edge with `rst` high, nobody holds a grant, and the next search
(below) starts at requester 0.

On each rising edge with `rst` low:

1. **Keep.** If the current holder still requests, it keeps the grant, unless
   it has already held the grant for 4 or more cycles in a row and some other
   requester is requesting. Once that happens, the holder loses the grant at
   the first edge where another requester is waiting.
2. **Pass on.** Otherwise the grant goes to the first requester whose `req` is
   high, searching in the order last+1, last+2, last+3, last (wrapping from 3
   back to 0), where `last` is the requester granted most recently. The new
   holder's count of cycles in a row starts again from 1.
3. **Idle.** If nobody requests, `grant` becomes 0. `last` is kept, so the next
   search still starts after the requester granted most recently.

Examples, starting just after reset:

- `req = 4'b0110` → the next grant goes to requester 1 (the search starts at 0).
- Requester 1 keeps requesting along with requester 2: requester 1 has the
  grant for 4 cycles, then requester 2 gets it.
- If requester 1 drops its request after 2 cycles, requester 2 gets the grant
  at the next edge.
