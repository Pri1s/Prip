"""Hidden reference test for updown_count: climbs to the top, falls to the bottom, loads near
the limit, and random traffic with occasional resets."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

LIMIT = 200


@cocotb.test()
async def updown_count_matches_model(dut):
    Clock(dut.clk, 10, unit="ns").start()
    for sig in (dut.en, dut.up, dut.load, dut.load_val):
        sig.value = 0
    dut.rst.value = 1
    await FallingEdge(dut.clk)

    rng = random.Random(7)
    # (rst, en, up, load, load_val)
    stream = [(0, 1, 1, 0, 0)] * 205 + [(0, 1, 0, 0, 0)] * 205   # saturate at both ends
    stream += [(0, 0, 0, 1, v) for v in (199, 200, 201, 255, 0, 1)] + [(0, 1, 1, 0, 0)] * 3
    stream += [(0, 1, 1, 1, 50), (0, 1, 0, 1, 7), (0, 0, 1, 0, 0)] * 2   # load beats count
    for _ in range(1500):
        stream.append((int(rng.random() < 0.01), int(rng.random() < 0.8), rng.randrange(2),
                       int(rng.random() < 0.03), rng.choice((rng.randrange(256), 199, 200, 201))))

    count = 0
    saw_top = saw_bottom = False
    for cycle, (rst, en, up, load, load_val) in enumerate(stream):
        dut.rst.value, dut.en.value, dut.up.value = rst, en, up
        dut.load.value, dut.load_val.value = load, load_val
        if rst:
            count = 0
        elif load:
            count = min(load_val, LIMIT)
        elif en and up:
            count = min(count + 1, LIMIT)
        elif en:
            count = max(count - 1, 0)
        saw_top |= count == LIMIT
        saw_bottom |= count == 0 and not rst
        await FallingEdge(dut.clk)
        assert int(dut.count.value) == count, f"cycle {cycle}: count"

    assert saw_top and saw_bottom, "stimulus missed a saturation case"
