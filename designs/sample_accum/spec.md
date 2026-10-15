# sample_accum

Adds up input samples in groups of three and reports each group's total.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | Clock; state changes on its rising edge |
| `rst` | in | 1 | Synchronous reset, active high |
| `in_valid` | in | 1 | `in_data` holds a sample to take this cycle |
| `in_data` | in | 8 | Input sample, unsigned |
| `out_valid` | out | 1 | High for one cycle when a group total is ready |
| `sum` | out | 10 | Total of the group just finished |

## Behavior

- A sample is taken on each rising edge where `in_valid` is high. Cycles with
  `in_valid` low are ignored and can appear anywhere, including inside a group.
- Samples are grouped in arrival order since reset: 1st–3rd, 4th–6th, and so
  on.
- On the edge that takes the third sample of a group, `sum` becomes the total
  of the group's three samples (at most 765, so it always fits), and
  `out_valid` is high for the following cycle only. The next sample starts a
  new group.
- `sum` is meaningful only while `out_valid` is high; at other times it may
  show anything.
- After a rising edge with `rst` high, `out_valid` is 0 and any partly
  collected group is discarded.
