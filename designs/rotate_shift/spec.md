# rotate_shift

An 8-bit barrel shifter. It moves the bits of `d` by 0 to 7 places in one step,
to the left or to the right, and either fills the vacated positions with zeros
or rotates the bits that fall off one end back in at the other. It has no clock
and no state: every output depends only on the current inputs.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `d` | in | 8 | Value to shift |
| `amt` | in | 3 | Number of places to move (0–7) |
| `left` | in | 1 | 1 = toward bit 7 (left), 0 = toward bit 0 (right) |
| `rot` | in | 1 | 1 = rotate, 0 = fill with zeros |
| `q` | out | 8 | Result |

## Behavior

| `left` | `rot` | `q` |
|---|---|---|
| 0 | 0 | `d >> amt`; the top `amt` bits of `q` are 0 |
| 1 | 0 | `d << amt`, keeping 8 bits; the bottom `amt` bits of `q` are 0 |
| 0 | 1 | `d` rotated right by `amt`: bit `i` of `q` is bit `(i + amt) mod 8` of `d` |
| 1 | 1 | `d` rotated left by `amt`: bit `i` of `q` is bit `(i - amt) mod 8` of `d` |

With `amt = 0`, `q` equals `d` in every mode.
