"""Hidden reference test for op_unit: directed corner cases plus random vectors."""

import itertools
import random

import cocotb
from cocotb.triggers import Timer

MASK = 0xFFFF


def to_signed(v):
    return v - 0x10000 if v & 0x8000 else v


def model(x, y, sel):
    """Returns (q, cf, vf) for one operation."""
    sh = y & 0xF
    cf = vf = 0
    if sel == 0:
        wide = x + y
        q, cf = wide & MASK, wide >> 16
        vf = int((x >> 15) == (y >> 15) and (q >> 15) != (x >> 15))
    elif sel == 1:
        q, cf = (x - y) & MASK, int(x < y)
        vf = int((x >> 15) != (y >> 15) and (q >> 15) != (x >> 15))
    elif sel == 2:
        q = x & y
    elif sel == 3:
        q = x | y
    elif sel == 4:
        q = x ^ y
    elif sel == 5:
        q = ~(x | y) & MASK
    elif sel == 6:
        q = int(to_signed(x) < to_signed(y))
    elif sel == 7:
        q = int(x < y)
    elif sel == 8:
        q = (x << sh) & MASK
    elif sel == 9:
        q = x >> sh
    elif sel == 10:
        q = (to_signed(x) >> sh) & MASK
    elif sel == 11:
        q = (y & 0xFF) << 8
    else:
        q = 0
    return q, cf, vf


@cocotb.test()
async def op_unit_matches_model(dut):
    corners = [0x0000, 0x0001, 0x7FFF, 0x8000, 0x8001, 0xFFFF, 0x00FF, 0x0F0F]
    rng = random.Random(1)
    vectors = list(itertools.product(corners, corners))
    vectors += [(rng.randrange(1 << 16), rng.randrange(1 << 16)) for _ in range(300)]

    for sel in range(16):
        for x, y in vectors:
            dut.x.value = x
            dut.y.value = y
            dut.sel.value = sel
            await Timer(1, unit="ns")
            q, cf, vf = model(x, y, sel)
            ctx = f"sel={sel} x={x:#06x} y={y:#06x}"
            assert int(dut.q.value) == q, f"{ctx}: q"
            assert int(dut.cf.value) == cf, f"{ctx}: cf"
            assert int(dut.vf.value) == vf, f"{ctx}: vf"
            assert int(dut.zf.value) == int(q == 0), f"{ctx}: zf"
            assert int(dut.nf.value) == q >> 15, f"{ctx}: nf"
