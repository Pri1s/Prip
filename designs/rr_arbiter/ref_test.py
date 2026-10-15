"""Hidden reference test for rr_arbiter: single requesters, everyone requesting (rotation and
hold limit), a long solo hold then a newcomer, idle gaps, mid-stream reset, random traffic."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

HOLD_LIMIT = 4


@cocotb.test()
async def rr_arbiter_matches_model(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst.value = 1
    dut.req.value = 0
    await FallingEdge(dut.clk)

    rng = random.Random(31)
    # (rst, req)
    stream = [(0, 0b0110)] * 3 + [(0, 0)] * 2 + [(0, 1 << i) for i in (3, 0, 2, 1)]
    stream += [(0, 0b1111)] * 24                               # rotation under the hold limit
    stream += [(0, 0b0100)] * 9 + [(0, 0b0101)] * 3 + [(0, 0b0001)] * 2
    stream += [(0, 0b1010), (0, 0b1000), (0, 0), (0, 0b1010)] + [(1, 0b1111), (0, 0b1111)] * 3
    stream += [(int(rng.random() < 0.005), rng.choice((rng.randrange(16), 0b1111, 1 << rng.randrange(4))))
               for _ in range(3000)]

    holder, last, run = None, 3, 0   # run = grant cycles in a row for the holder
    switches_by_limit = 0
    for cycle, (rst, req) in enumerate(stream):
        dut.rst.value, dut.req.value = rst, req
        if rst:
            holder, last, run = None, 3, 0
        else:
            others = req & ~(0 if holder is None else 1 << holder)
            if holder is not None and req >> holder & 1 and (run < HOLD_LIMIT or not others):
                run += 1
            else:
                nxt = next(((last + k) % 4 for k in range(1, 5) if req >> ((last + k) % 4) & 1), None)
                if holder is not None and req >> holder & 1:
                    switches_by_limit += 1
                if nxt is None:
                    holder, run = None, 0
                else:
                    holder, last, run = nxt, nxt, 1

        await FallingEdge(dut.clk)
        expect = 0 if holder is None else 1 << holder
        assert int(dut.grant.value) == expect, f"cycle {cycle}: grant (req {req:04b})"

    assert switches_by_limit >= 10, "stimulus rarely hit the hold limit"
