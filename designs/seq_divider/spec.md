# seq_divider

Divides one 6-bit number by another over several clock cycles, giving a
quotient and a remainder. The numbers can be unsigned (0 to 63) or signed
two's-complement (−32 to 31).

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | Clock; state changes on its rising edge |
| `rst` | in | 1 | Synchronous reset, active high |
| `start` | in | 1 | Request a division of `dividend` by `divisor` |
| `is_signed` | in | 1 | 1 = signed two's-complement operands, 0 = unsigned |
| `dividend` | in | 6 | Number to divide |
| `divisor` | in | 6 | Number to divide by |
| `ack` | in | 1 | The result has been read; free the divider |
| `ready` | out | 1 | High when a new division can be accepted |
| `done` | out | 1 | High while a finished result is on `quotient` and `remainder` |
| `quotient` | out | 6 | Quotient of the last accepted division |
| `remainder` | out | 6 | Remainder of the last accepted division |

## Handshake and timing

- After reset, `ready` is high and `done` is low.
- A division is accepted on a rising edge where `ready` and `start` are both
  high. `dividend`, `divisor` and `is_signed` are captured on that edge; they
  may change freely afterwards. `ready` goes low.
- The divider then works for 6 cycles: `done` goes high on the 6th rising
  edge after the accepting edge.
- `done` stays high, and the result stays unchanged, until a rising edge where
  `ack` is high. After that edge `done` is low and `ready` is high again.
  `ack` has no effect while `done` is low, and `start` has no effect while
  `ready` is low.
- `quotient` and `remainder` are meaningful only while `done` is high; at other
  times they may show anything.
- A rising edge with `rst` high abandons any division in progress and returns
  to `ready` high, `done` low.

## Results

- Unsigned (`is_signed = 0`): `quotient = dividend / divisor` and
  `remainder = dividend % divisor`, rounding down.
- Signed (`is_signed = 1`): the quotient rounds toward zero and the remainder
  has the same sign as the dividend (or is zero), so
  `dividend = quotient × divisor + remainder`. Example: −7 / 2 gives quotient
  −3 and remainder −1. The one quotient that doesn't fit, −32 / −1 = +32, is
  reported as its low 6 bits, `6'b100000`.
- Division by zero (either mode): `quotient` is all ones (`6'h3F`) and
  `remainder` equals `dividend`.
