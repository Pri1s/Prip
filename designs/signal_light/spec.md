# signal_light

Controls one traffic signal. The light cycles red → green → yellow → red with
fixed durations. A pedestrian button can cut a long green short.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | Clock; state changes on its rising edge |
| `rst` | in | 1 | Synchronous reset, active high |
| `ped_req` | in | 1 | Pedestrian button is pressed this cycle |
| `red` | out | 1 | Red light on |
| `yellow` | out | 1 | Yellow light on |
| `green` | out | 1 | Green light on |
| `remaining` | out | 5 | Cycles left in the current light after this one |

## Behavior

- Exactly one of `red`, `yellow`, `green` is on at any time. The lights depend
  only on stored state, not directly on `ped_req`.
- Without pedestrian requests, red lasts 8 cycles, green 24 cycles and yellow
  3 cycles, then the sequence repeats.
- `remaining` counts down by 1 every cycle. In the last cycle of a light it is
  0, and on the next rising edge the light changes and `remaining` becomes the
  new light's duration minus 1 (7 for red, 23 for green, 2 for yellow).
- After a rising edge with `rst` high, the light is red with `remaining = 7`:
  a fresh 8-cycle red.
- Pedestrian request: on a rising edge where the light is green, `ped_req` is
  high and `remaining` is above 4, `remaining` becomes 4, so green lasts 5 more
  cycles counting the cycle right after the edge. If `remaining` is 4 or less,
  the request has no effect. Requests during red or yellow are ignored and are
  not remembered.
