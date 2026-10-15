# updown_count

An 8-bit counter that counts up or down between 0 and 200. It sticks at either
end instead of wrapping around, and it can be loaded with a new value.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | Clock; state changes on its rising edge |
| `rst` | in | 1 | Synchronous reset, active high |
| `en` | in | 1 | Count this cycle |
| `up` | in | 1 | Direction when counting: 1 = up, 0 = down |
| `load` | in | 1 | Load `load_val` this cycle |
| `load_val` | in | 8 | Value to load |
| `count` | out | 8 | Current count (0–200) |

## Behavior

On each rising edge, the first rule that applies decides the new `count`:

1. `rst` high: `count` becomes 0.
2. `load` high: `count` becomes `load_val`, or 200 if `load_val` is above 200.
   `en` and `up` are ignored this cycle.
3. `en` high and `up` high: `count` goes up by 1, unless it is already 200, in
   which case it stays at 200.
4. `en` high and `up` low: `count` goes down by 1, unless it is already 0, in
   which case it stays at 0.
5. Otherwise `count` keeps its value.

`count` is never above 200.
