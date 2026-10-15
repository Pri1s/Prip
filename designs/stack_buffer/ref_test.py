"""Hidden reference test for stack_buffer: fill past full, drain past empty, push+pop together,
mid-stream reset, and random traffic."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

DEPTH = 6


@cocotb.test()
async def stack_buffer_matches_model(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst.value = 1
    dut.push.value = dut.pop.value = dut.din.value = 0
    await FallingEdge(dut.clk)

    rng = random.Random(11)
    # (rst, push, pop, din)
    stream = [(0, 1, 0, v) for v in range(9)]                  # pushes past full
    stream += [(0, 0, 1, 0)] * 8                               # pops past empty
    stream += [(0, 1, 1, 5), (0, 1, 0, 9), (0, 1, 1, 3), (0, 0, 1, 0), (0, 1, 1, 0xA)]
    stream += [(0, 1, 0, v) for v in (1, 2, 3)] + [(1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 4), (0, 0, 1, 0)]
    for _ in range(2000):
        bias = rng.choice((0.3, 0.5, 0.7))
        stream.append((int(rng.random() < 0.01), int(rng.random() < bias),
                       int(rng.random() < 1 - bias), rng.randrange(16)))

    stack, dout = [], 0
    saw_full = saw_empty_pop = False
    for cycle, (rst, push, pop, din) in enumerate(stream):
        dut.rst.value, dut.push.value, dut.pop.value, dut.din.value = rst, push, pop, din
        if rst:
            stack, dout = [], 0
        elif pop and stack:
            dout = stack.pop()
        elif push and len(stack) < DEPTH:
            stack.append(din)
        else:
            saw_empty_pop |= pop and not stack
        saw_full |= len(stack) == DEPTH

        await FallingEdge(dut.clk)
        await Timer(1, unit="ns")
        ctx = f"cycle {cycle}"
        assert int(dut.empty.value) == int(not stack), f"{ctx}: empty"
        assert int(dut.full.value) == int(len(stack) == DEPTH), f"{ctx}: full"
        assert int(dut.dout.value) == dout, f"{ctx}: dout"
        if stack:
            assert int(dut.top.value) == stack[-1], f"{ctx}: top"

    assert saw_full and saw_empty_pop, "stimulus missed the full or empty-pop cases"
