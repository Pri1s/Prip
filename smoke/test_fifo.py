"""cocotb smoke test: random push/pop against a Python queue model."""

import random
from collections import deque
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from cocotb_tools.runner import get_runner

DEPTH = 4
HERE = Path(__file__).resolve().parent


@cocotb.test()
async def fifo_matches_queue_model(dut):
    # Drive and sample on the falling edge so values are stable around each rising edge.
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst.value = 1
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.wr_data.value = 0
    for _ in range(2):
        await FallingEdge(dut.clk)
    dut.rst.value = 0

    model = deque()
    rng = random.Random(0)
    saw_full = False
    for cycle in range(300):
        await FallingEdge(dut.clk)
        assert int(dut.empty.value) == (len(model) == 0), f"cycle {cycle}: empty flag"
        assert int(dut.full.value) == (len(model) == DEPTH), f"cycle {cycle}: full flag"
        if model:
            assert int(dut.rd_data.value) == model[0], f"cycle {cycle}: rd_data"
        saw_full |= len(model) == DEPTH

        wr, rd, data = rng.random() < 0.5, rng.random() < 0.5, rng.randrange(256)
        dut.wr_en.value = int(wr)
        dut.rd_en.value = int(rd)
        dut.wr_data.value = data
        do_wr, do_rd = wr and len(model) < DEPTH, rd and len(model) > 0
        if do_rd:
            model.popleft()
        if do_wr:
            model.append(data)

    assert saw_full, "stimulus never filled the FIFO"


def test_fifo():
    runner = get_runner("icarus")
    runner.build(
        sources=[HERE / "fifo.v"],
        hdl_toplevel="fifo",
        build_dir=HERE / "sim_build",
        timescale=("1ns", "1ps"),
        always=True,
    )
    runner.test(hdl_toplevel="fifo", test_module="test_fifo", test_dir=HERE / "sim_build")
