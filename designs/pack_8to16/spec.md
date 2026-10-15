# pack_8to16

Collects a stream of bytes and joins each pair into one 16-bit word. The first
byte of a pair becomes the low half of the word.

## Ports

| Port | Dir | Width | Meaning |
|---|---|---|---|
| `clk` | in | 1 | Clock; state changes on its rising edge |
| `rst` | in | 1 | Synchronous reset, active high |
| `in_valid` | in | 1 | `in_byte` holds a byte to take this cycle |
| `in_byte` | in | 8 | Input byte |
| `out_valid` | out | 1 | High for one cycle when a new word has been completed |
| `out_word` | out | 16 | Most recently completed word |
| `waiting` | out | 1 | High while the first byte of a pair is held, waiting for its partner |

## Behavior

- A byte is taken on each rising edge where `in_valid` is high. Cycles with
  `in_valid` low are ignored and can appear anywhere, including between the two
  bytes of a pair.
- Bytes are paired in arrival order: 1st with 2nd, 3rd with 4th, and so on,
  counting from reset.
- On the edge that takes the first byte of a pair, `waiting` goes high.
- On the edge that takes the second byte, `waiting` goes low, `out_word`
  becomes `{second byte, first byte}` (second byte in bits 15–8), and
  `out_valid` is high for the following cycle only.
- `out_word` keeps its value until the next word is completed.
- After a rising edge with `rst` high: no byte is held (`waiting = 0`),
  `out_valid = 0` and `out_word = 0`. A half-finished pair is discarded.
