# op_unit

A 16-bit arithmetic and logic unit. It has no clock and no state: every output
depends only on the current inputs.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `x` | in | 16 | First operand |
| `y` | in | 16 | Second operand |
| `sel` | in | 4 | Operation select (table below) |
| `q` | out | 16 | Result |
| `cf` | out | 1 | Carry / borrow flag |
| `vf` | out | 1 | Signed overflow flag |
| `zf` | out | 1 | High when `q` is zero |
| `nf` | out | 1 | Copy of the top bit of `q` |

## Operations

| `sel` | Name | `q` |
|---|---|---|
| 0 | ADD | `x + y`, keeping the low 16 bits |
| 1 | SUB | `x - y`, keeping the low 16 bits |
| 2 | AND | bitwise `x & y` |
| 3 | OR | bitwise `x \| y` |
| 4 | XOR | bitwise `x ^ y` |
| 5 | NOR | bitwise `~(x \| y)` |
| 6 | SLT | 1 if `x < y` comparing as signed two's-complement numbers, else 0 |
| 7 | SLTU | 1 if `x < y` comparing as unsigned numbers, else 0 |
| 8 | SHL | `x` shifted left by `y[3:0]` places, filling with zeros |
| 9 | SHR | `x` shifted right by `y[3:0]` places, filling with zeros |
| 10 | SAR | `x` shifted right by `y[3:0]` places, filling with copies of `x[15]` |
| 11 | LDH | the low byte of `y` placed in the high byte of `q`; the low byte of `q` is zero |
| 12–15 | — | 0 |

## Flags

- `cf`: for ADD, the carry out of an unsigned 16-bit addition. For SUB, set when
  `y` is larger than `x` as unsigned numbers (a borrow is needed). Zero for every
  other operation.
- `vf`: for ADD and SUB, set when the signed result does not fit in 16 bits.
  Zero for every other operation.
- `zf` and `nf` are computed from `q` for every operation, including the unused
  `sel` values.
