"""Hidden reference test for pack_8to16: back-to-back bytes, gaps inside and between pairs,
reset with a byte held, and random traffic."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge


@cocotb.test()
async def pack_8to16_matches_model(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst.value = 1
    dut.in_valid.value = dut.in_byte.value = 0
    await FallingEdge(dut.clk)

    rng = random.Random(17)
    # (rst, in_valid, in_byte)
    stream = [(0, 1, b) for b in (0x11, 0x22, 0x33, 0x44, 0x55, 0x66)]
    stream += [(0, 1, 0xA1), (0, 0, 0xFF), (0, 0, 0xEE), (0, 1, 0xB2), (0, 0, 0x00)]
    stream += [(0, 1, 0xC3), (1, 0, 0), (0, 1, 0xD4), (0, 1, 0xE5), (0, 1, 0x0F), (1, 1, 0x99)]
    stream += [(int(rng.random() < 0.01), int(rng.random() < rng.choice((0.3, 0.7, 1.0))),
                rng.randrange(256)) for _ in range(2000)]

    held, waiting, out_valid, out_word = 0, 0, 0, 0
    words = 0
    for cycle, (rst, valid, byte) in enumerate(stream):
        dut.rst.value, dut.in_valid.value, dut.in_byte.value = rst, valid, byte
        if rst:
            held, waiting, out_valid, out_word = 0, 0, 0, 0
        else:
            out_valid = int(valid and waiting)
            if valid and waiting:
                out_word, waiting = (byte << 8) | held, 0
                words += 1
            elif valid:
                held, waiting = byte, 1

        await FallingEdge(dut.clk)
        ctx = f"cycle {cycle}"
        assert int(dut.waiting.value) == waiting, f"{ctx}: waiting"
        assert int(dut.out_valid.value) == out_valid, f"{ctx}: out_valid"
        assert int(dut.out_word.value) == out_word, f"{ctx}: out_word"

    assert words > 100, "stimulus completed too few words"
