"""Hidden reference test for token_bucket: bursts, idle refills, mid-stream reset, random traffic."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

MAX_TOKENS = 3
REFILL_PERIOD = 5


@cocotb.test()
async def token_bucket_matches_model(dut):
    # Drive on the falling edge; check the same-cycle grant just after driving,
    # and the registered level after the next rising edge.
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst.value = 1
    dut.req.value = 0
    await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)

    rng = random.Random(3)
    stream = [(0, 1)] * 8 + [(0, 0)] * 18 + [(0, 1)] * 12  # drain, refill to full, drain again
    stream += [(0, 1), (0, 1), (1, 0), (0, 1)] + [(0, 1)] * 10  # reset mid-burst
    stream += [(int(rng.random() < 0.02), int(rng.random() < rng.choice((0.2, 0.5, 0.9))))
               for _ in range(800)]

    level, tick = MAX_TOKENS, 0
    saw_empty = saw_lost_refill = False
    for cycle, (rst, req) in enumerate(stream):
        dut.rst.value = rst
        dut.req.value = req
        await Timer(1, unit="ns")
        grant = int(req and level > 0)
        assert int(dut.grant.value) == grant, f"cycle {cycle}: grant (level {level})"

        if rst:
            level, tick = MAX_TOKENS, 0
        else:
            refill = tick == REFILL_PERIOD - 1
            tick = 0 if refill else tick + 1
            level -= grant
            saw_lost_refill |= refill and level == MAX_TOKENS
            if refill and level < MAX_TOKENS:
                level += 1
        saw_empty |= level == 0

        await FallingEdge(dut.clk)
        assert int(dut.level.value) == level, f"cycle {cycle}: level"

    assert saw_empty and saw_lost_refill, "stimulus missed the empty or full-bucket cases"
