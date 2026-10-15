# secded_decode

Decodes one 8-bit codeword of an error-correcting code that protects 4 data
bits. It corrects any single flipped bit and detects any two flipped bits
(single-error-correct, double-error-detect, "SECDED"). It has no clock and no
state: every output depends only on the current input.

## Codeword layout

| `cw` bit | 7 | 6 | 5 | 4 | 3 | 2 | 1 | 0 |
|---|---|---|---|---|---|---|---|---|
| Holds | d3 | d2 | d1 | p4 | d0 | p2 | p1 | p0 |

- Bits 1–7 form a Hamming(7,4) code: bit `i` of `cw` is Hamming position `i`.
  Check bit `p1` makes the XOR of positions 1, 3, 5, 7 zero; `p2` does the same
  for positions 2, 3, 6, 7; `p4` for positions 4, 5, 6, 7.
- `p0` makes the XOR of all 8 bits zero (even overall parity).

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `cw` | in | 8 | Received codeword, possibly with flipped bits |
| `data` | out | 4 | Decoded data `{d3, d2, d1, d0}` |
| `fixed` | out | 1 | High when exactly one bit was found flipped and was corrected |
| `double_err` | out | 1 | High when two flipped bits were detected; `data` is not corrected |

## Behavior

Let the syndrome `s` be the 3-bit number whose bit 0 is the XOR of positions
1, 3, 5, 7, bit 1 the XOR of positions 2, 3, 6, 7, and bit 2 the XOR of
positions 4, 5, 6, 7. Let `odd` be the XOR of all 8 bits of `cw`.

| `odd` | `s` | Meaning | `data` | `fixed` | `double_err` |
|---|---|---|---|---|---|
| 0 | 0 | no error | data bits of `cw` | 0 | 0 |
| 1 | 0 | `p0` itself flipped | data bits of `cw` | 1 | 0 |
| 1 | 1–7 | bit `s` of `cw` flipped | data bits after flipping bit `s` back | 1 | 0 |
| 0 | 1–7 | two bits flipped | data bits of `cw`, uncorrected | 0 | 1 |

`fixed` and `double_err` are never both high. With three or more flipped bits
the decoder may report a single error or a wrong `data`; that is expected.
