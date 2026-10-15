# clock_counter

A scaled-down clock with three counters chained together: `sec` counts 0–9,
`min` counts 0–5 and `hr` counts 0–11. Each enabled cycle is one tick of `sec`.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | Clock; state changes on its rising edge |
| `rst` | in | 1 | Synchronous reset, active high |
| `run` | in | 1 | Advance the clock this cycle |
| `sec` | out | 4 | Seconds digit, 0–9 |
| `min` | out | 3 | Minutes, 0–5 |
| `hr` | out | 4 | Hours, 0–11 |

## Behavior

- A rising edge with `rst` high sets all three counters to 0.
- On a rising edge with `rst` low and `run` high, the clock advances by one
  tick:
  - `sec` goes up by 1, except that 9 goes back to 0;
  - `min` goes up by 1 only on a tick where `sec` goes from 9 to 0, except
    that 5 goes back to 0;
  - `hr` goes up by 1 only on a tick where `min` goes from 5 to 0, except that
    11 goes back to 0.
- With `run` low, nothing changes.
- So the clock reads `hr:min:sec`, and after 720 ticks it is back at 0:0:0.
  For example, the tick after 3:5:9 gives 4:0:0, and the tick after 11:5:9
  gives 0:0:0.
