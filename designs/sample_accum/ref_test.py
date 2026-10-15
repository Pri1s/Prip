"""Hidden reference test for sample_accum: back-to-back groups, gaps inside groups, maximum
samples, reset with a partial group, and random traffic."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge


@cocotb.test()
async def sample_accum_matches_model(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst.value = 1
    dut.in_valid.value = dut.in_data.value = 0
    await FallingEdge(dut.clk)

    rng = random.Random(23)
    # (rst, in_valid, in_data)
    stream = [(0, 1, v) for v in (1, 2, 3, 10, 20, 30, 255, 255, 255)]
    stream += [(0, 1, 7), (0, 0, 99), (0, 0, 99), (0, 1, 8), (0, 0, 99), (0, 1, 9), (0, 0, 0)]
    stream += [(0, 1, 50), (0, 1, 60), (1, 1, 70), (0, 1, 1), (0, 1, 2), (0, 1, 4), (0, 0, 0)]
    stream += [(int(rng.random() < 0.01), int(rng.random() < rng.choice((0.3, 0.8, 1.0))),
                rng.choice((rng.randrange(256), 255, 0))) for _ in range(2000)]

    group, out_valid, total = [], 0, None
    groups = 0
    for cycle, (rst, valid, data) in enumerate(stream):
        dut.rst.value, dut.in_valid.value, dut.in_data.value = rst, valid, data
        if rst:
            group, out_valid = [], 0
        else:
            out_valid = 0
            if valid:
                group.append(data)
                if len(group) == 3:
                    total, group, out_valid = sum(group), [], 1
                    groups += 1

        await FallingEdge(dut.clk)
        ctx = f"cycle {cycle}"
        assert int(dut.out_valid.value) == out_valid, f"{ctx}: out_valid"
        if out_valid:
            assert int(dut.sum.value) == total, f"{ctx}: sum"

    assert groups > 100, "stimulus finished too few groups"
