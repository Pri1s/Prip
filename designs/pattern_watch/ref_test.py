"""Hidden reference test for pattern_watch: directed overlaps, mid-stream reset, random stream."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

PATTERN = (1, 1, 0, 1)


@cocotb.test()
async def pattern_watch_matches_model(dut):
    # Drive and sample on the falling edge so values are stable around each rising edge.
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst.value = 1
    dut.din.value = 0
    await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)

    rng = random.Random(2)
    directed = [1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1]
    stream = [(0, b) for b in directed]
    stream += [(1, 1), (0, 0), (0, 1)]  # reset in the middle of a partial match
    stream += [(0, b) for b in [1, 1, 0, 1]]
    stream += [(int(rng.random() < 0.03), int(rng.random() < 0.6)) for _ in range(600)]

    history = []
    hits = 0
    for cycle, (rst, bit) in enumerate(stream):
        dut.rst.value = rst
        dut.din.value = bit
        await FallingEdge(dut.clk)
        history = [] if rst else (history + [bit])[-4:]
        expected = int(tuple(history) == PATTERN)
        hits += expected
        assert int(dut.seen.value) == expected, f"cycle {cycle}: seen (history {history})"

    assert hits >= 5, "stimulus produced too few matches"
