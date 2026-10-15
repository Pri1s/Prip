"""Hidden reference test for signal_light: full undisturbed cycles, requests at and around the
cut-off, requests during red and yellow, mid-cycle reset, and random presses."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

DURATION = {"red": 8, "green": 24, "yellow": 3}
NEXT = {"red": "green", "green": "yellow", "yellow": "red"}
PED_LEFT = 4


@cocotb.test()
async def signal_light_matches_model(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst.value = 1
    dut.ped_req.value = 0
    await FallingEdge(dut.clk)

    rng = random.Random(13)
    # (rst, ped_req)
    stream = [(0, 0)] * 80                                     # two full cycles
    stream += [(0, 0)] * 9 + [(0, 1)] + [(0, 0)] * 30          # press early in green
    stream += [(0, 1)] * 70                                    # held through every light
    stream += [(0, 0)] * 12 + [(1, 0)] + [(0, 0)] * 20         # reset mid-green
    stream += [(int(rng.random() < 0.005), int(rng.random() < rng.choice((0.02, 0.1, 0.5))))
               for _ in range(3000)]

    light, left = "red", DURATION["red"] - 1
    shortened = 0
    for cycle, (rst, ped) in enumerate(stream):
        dut.rst.value, dut.ped_req.value = rst, ped
        if rst:
            light, left = "red", DURATION["red"] - 1
        elif left == 0:
            light = NEXT[light]
            left = DURATION[light] - 1
        elif light == "green" and ped and left > PED_LEFT:
            left = PED_LEFT
            shortened += 1
        else:
            left -= 1

        await FallingEdge(dut.clk)
        ctx = f"cycle {cycle}"
        for name in DURATION:
            assert int(getattr(dut, name).value) == int(light == name), f"{ctx}: {name}"
        assert int(dut.remaining.value) == left, f"{ctx}: remaining"

    assert shortened >= 5, "stimulus rarely shortened a green"
