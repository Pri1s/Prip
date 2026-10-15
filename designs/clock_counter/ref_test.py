"""Hidden reference test for clock_counter: two full 720-tick cycles, pauses at every carry
boundary, a reset mid-hour, and long random stretches with run mostly high."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge


@cocotb.test()
async def clock_counter_matches_model(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst.value = 1
    dut.run.value = 0
    await FallingEdge(dut.clk)

    rng = random.Random(19)
    # (rst, run)
    stream = [(0, 1)] * 1450                                   # two full cycles
    stream += [(0, int(rng.random() < 0.8)) for _ in range(1600)]  # wraps with pauses mixed in
    stream += [(0, 1)] * 200 + [(1, 1)] + [(0, 1)] * 100
    stream += [(int(rng.random() < 0.0005), int(rng.random() < 0.95)) for _ in range(2500)]

    sec = mn = hr = 0
    hr_wraps = 0
    for cycle, (rst, run) in enumerate(stream):
        dut.rst.value, dut.run.value = rst, run
        if rst:
            sec = mn = hr = 0
        elif run:
            sec = (sec + 1) % 10
            if sec == 0:
                mn = (mn + 1) % 6
                if mn == 0:
                    hr = (hr + 1) % 12
                    hr_wraps += hr == 0

        await FallingEdge(dut.clk)
        ctx = f"cycle {cycle} (expect {hr}:{mn}:{sec})"
        assert int(dut.sec.value) == sec, f"{ctx}: sec"
        assert int(dut.min.value) == mn, f"{ctx}: min"
        assert int(dut.hr.value) == hr, f"{ctx}: hr"

    assert hr_wraps >= 3, "stimulus wrapped the hour counter too rarely"
