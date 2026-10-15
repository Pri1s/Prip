# stack_buffer

A stack (last in, first out) that holds up to six 4-bit values. A pop returns
the value pushed most recently.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | Clock; state changes on its rising edge |
| `rst` | in | 1 | Synchronous reset, active high |
| `push` | in | 1 | Push `din` this cycle |
| `pop` | in | 1 | Pop the top entry this cycle |
| `din` | in | 4 | Value to push |
| `dout` | out | 4 | Value taken by the most recent successful pop |
| `top` | out | 4 | The entry on top of the stack right now (not removed) |
| `empty` | out | 1 | High when the stack holds no entries |
| `full` | out | 1 | High when the stack holds six entries |

## Behavior

On each rising edge, the first rule that applies is carried out:

1. `rst` high: the stack becomes empty and `dout` becomes 0.
2. `pop` high and the stack not empty: the top entry is removed and appears on
   `dout` after the edge.
3. `push` high and the stack not full: `din` is placed on top of the stack.
4. Otherwise nothing changes. A pop of an empty stack and a push to a full
   stack are ignored, and `dout` keeps its value.

So when `push` and `pop` are both high on a non-empty stack, only the pop
happens; on an empty stack, only the push happens.

- `empty` and `full` follow the number of entries held and change right after
  the edge that changes it.
- `top` shows the newest entry without removing it, and changes as soon as a
  push or pop changes the stack. Its value is meaningful only while `empty` is
  low; while the stack is empty `top` may show anything.
- Reset does not clear the stored values, but after reset the old values are
  never visible: only entries pushed since the reset can reach `top` or `dout`.
