"""Hidden reference test for secded_decode: all 256 codewords, plus an encode/corrupt/decode check."""

import cocotb
from cocotb.triggers import Timer


def bit(v, i):
    return (v >> i) & 1


def model(cw):
    """Returns (data, fixed, double_err), computed from the spec's table."""
    s = (bit(cw, 1) ^ bit(cw, 3) ^ bit(cw, 5) ^ bit(cw, 7)) \
        | (bit(cw, 2) ^ bit(cw, 3) ^ bit(cw, 6) ^ bit(cw, 7)) << 1 \
        | (bit(cw, 4) ^ bit(cw, 5) ^ bit(cw, 6) ^ bit(cw, 7)) << 2
    odd = bin(cw).count("1") & 1
    if odd:
        cw ^= 1 << s
    data = bit(cw, 3) | bit(cw, 5) << 1 | bit(cw, 6) << 2 | bit(cw, 7) << 3
    return data, odd, int(not odd and s != 0)


def encode(d):
    d0, d1, d2, d3 = (bit(d, i) for i in range(4))
    p1, p2, p4 = d0 ^ d1 ^ d3, d0 ^ d2 ^ d3, d1 ^ d2 ^ d3
    cw = p1 << 1 | p2 << 2 | d0 << 3 | p4 << 4 | d1 << 5 | d2 << 6 | d3 << 7
    return cw | (bin(cw).count("1") & 1)


async def decode(dut, cw):
    dut.cw.value = cw
    await Timer(1, unit="ns")
    return int(dut.data.value), int(dut.fixed.value), int(dut.double_err.value)


@cocotb.test()
async def secded_decode_matches_model(dut):
    for cw in range(256):
        assert await decode(dut, cw) == model(cw), f"cw={cw:#010b}"


@cocotb.test()
async def secded_decode_corrects_and_detects(dut):
    # Independent of the table model: encode real data, then flip 0, 1 or 2 bits.
    for d in range(16):
        cw = encode(d)
        assert await decode(dut, cw) == (d, 0, 0), f"d={d}: clean codeword"
        for i in range(8):
            assert await decode(dut, cw ^ (1 << i)) == (d, 1, 0), f"d={d}: bit {i} flipped"
            for j in range(i + 1, 8):
                _, fixed, dbl = await decode(dut, cw ^ (1 << i) ^ (1 << j))
                assert (fixed, dbl) == (0, 1), f"d={d}: bits {i},{j} flipped"
