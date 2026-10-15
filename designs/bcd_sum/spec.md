# bcd_sum

Adds two 2-digit decimal numbers written in binary-coded decimal (BCD), plus a
carry-in. It has no clock and no state: every output depends only on the
current inputs.

In BCD each decimal digit takes 4 bits, holding a value from 0 to 9. An 8-bit
value holds two digits: bits 7–4 are the tens digit and bits 3–0 are the ones
digit. For example, decimal 47 is `8'h47`.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `a` | in | 8 | First number, two BCD digits |
| `b` | in | 8 | Second number, two BCD digits |
| `cin` | in | 1 | Carry-in: adds 1 to the total |
| `sum` | out | 8 | Last two decimal digits of `a + b + cin`, in BCD |
| `cout` | out | 1 | High when `a + b + cin` is 100 or more |
| `bad` | out | 1 | High when any of the four input digits is above 9 |

## Behavior

- When every input digit is 0–9, `sum` and `cout` give the decimal total
  `a + b + cin` (0 to 199): `cout` is the hundreds digit and `sum` holds the
  tens and ones digits in BCD. Example: `a = 8'h58`, `b = 8'h67`, `cin = 1`
  gives 126, so `cout = 1` and `sum = 8'h26`.
- When any input digit is 10–15, the input is not valid BCD: `bad` is high and
  `sum` and `cout` are both 0.
- `bad` depends only on `a` and `b`, never on `cin`.
