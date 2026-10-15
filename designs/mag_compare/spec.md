# mag_compare

Compares two 6-bit numbers and reports whether the first is greater than, equal
to, or less than the second. The numbers can be read as unsigned (0 to 63) or as
signed two's-complement (−32 to 31). It has no clock and no state: every output
depends only on the current inputs.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `a` | in | 6 | First number |
| `b` | in | 6 | Second number |
| `is_signed` | in | 1 | 1 = compare as signed two's-complement, 0 = as unsigned |
| `gt` | out | 1 | High when `a > b` |
| `eq` | out | 1 | High when `a == b` |
| `lt` | out | 1 | High when `a < b` |

## Behavior

- Exactly one of `gt`, `eq`, `lt` is high for every input.
- In signed mode, bit 5 is the sign bit: `6'b100000` is −32 and `6'b111111` is
  −1. So with `is_signed = 1`, `a = 6'b111111` (−1) is less than `b = 6'd1`;
  with `is_signed = 0` the same `a` (63) is greater.
- `eq` does not depend on `is_signed`.
