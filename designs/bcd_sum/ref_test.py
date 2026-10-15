"""Hidden reference test for bcd_sum: every valid input pair exhaustively, plus invalid digits."""

import random

import cocotb
from cocotb.triggers import Timer


def from_bcd(v):
    return (v >> 4) * 10 + (v & 0xF)


def is_bcd(v):
    return (v >> 4) <= 9 and (v & 0xF) <= 9


def model(a, b, cin):
    """Returns (sum, cout, bad)."""
    if not (is_bcd(a) and is_bcd(b)):
        return 0, 0, 1
    total = from_bcd(a) + from_bcd(b) + cin
    low = total % 100
    return ((low // 10) << 4) | (low % 10), total // 100, 0


@cocotb.test()
async def bcd_sum_matches_model(dut):
    valid = [((t << 4) | o) for t in range(10) for o in range(10)]
    vectors = [(a, b, c) for a in valid for b in valid for c in (0, 1)]
    rng = random.Random(5)
    vectors += [(rng.randrange(256), rng.randrange(256), rng.randrange(2)) for _ in range(3000)]

    for a, b, cin in vectors:
        dut.a.value = a
        dut.b.value = b
        dut.cin.value = cin
        await Timer(1, unit="ns")
        s, cout, bad = model(a, b, cin)
        ctx = f"a={a:#04x} b={b:#04x} cin={cin}"
        assert int(dut.bad.value) == bad, f"{ctx}: bad"
        assert int(dut.sum.value) == s, f"{ctx}: sum"
        assert int(dut.cout.value) == cout, f"{ctx}: cout"
