"""Hidden reference test for seq_divider: every operand pair in both modes once, handshake
timing (late ack, early start, inputs changing mid-division), and reset during a division."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

W = 6
MASK = (1 << W) - 1
LATENCY = 6  # rising edges after the accepting edge until done


def signed(v):
    return v - (1 << W) if v >> (W - 1) else v


def model(dvd, dvs, is_signed):
    """Returns (quotient, remainder) as W-bit values."""
    if dvs == 0:
        return MASK, dvd
    if not is_signed:
        return dvd // dvs, dvd % dvs
    a, b = signed(dvd), signed(dvs)
    q = abs(a) // abs(b)
    q = -q if (a < 0) != (b < 0) else q
    return q & MASK, (a - q * b) & MASK


async def edge(dut, n=1):
    for _ in range(n):
        await FallingEdge(dut.clk)


async def divide(dut, dvd, dvs, is_signed, ack_delay=0):
    """Starts one division, checks the handshake and the result, then acks it."""
    assert int(dut.ready.value) == 1, "ready before start"
    dut.start.value, dut.dividend.value, dut.divisor.value, dut.is_signed.value = 1, dvd, dvs, is_signed
    await edge(dut)
    dut.start.value = 1  # held high: must be ignored while busy
    dut.dividend.value, dut.divisor.value, dut.is_signed.value = dvs, dvd, 1 - is_signed
    for i in range(LATENCY):
        assert (int(dut.ready.value), int(dut.done.value)) == (0, 0), f"busy after edge {i}"
        await edge(dut)
    dut.start.value = 0
    ctx = f"{'s' if is_signed else 'u'} {dvd}/{dvs}"
    for i in range(ack_delay + 1):
        assert int(dut.done.value) == 1, f"{ctx}: done"
        assert int(dut.ready.value) == 0, f"{ctx}: ready while done"
        q, r = model(dvd, dvs, is_signed)
        assert (int(dut.quotient.value), int(dut.remainder.value)) == (q, r), f"{ctx}: result"
        dut.ack.value = int(i == ack_delay)
        await edge(dut)
    dut.ack.value = 0
    assert (int(dut.ready.value), int(dut.done.value)) == (1, 0), f"{ctx}: after ack"


@cocotb.test()
async def seq_divider_matches_model(dut):
    Clock(dut.clk, 10, unit="ns").start()
    for sig in (dut.start, dut.is_signed, dut.dividend, dut.divisor, dut.ack):
        sig.value = 0
    dut.rst.value = 1
    await edge(dut)
    dut.rst.value = 0
    await edge(dut)

    rng = random.Random(29)
    pairs = [(a, b, s) for s in (0, 1) for a in range(64) for b in range(64)]
    rng.shuffle(pairs)
    for dvd, dvs, s in pairs:
        await divide(dut, dvd, dvs, s, ack_delay=rng.choice((0, 0, 1, 3)))

    # ack while idle does nothing; reset mid-division abandons it.
    dut.ack.value = 1
    await edge(dut, 2)
    dut.ack.value = 0
    assert (int(dut.ready.value), int(dut.done.value)) == (1, 0), "ack while idle"
    dut.start.value, dut.dividend.value, dut.divisor.value = 1, 40, 3
    await edge(dut, 3)
    dut.start.value, dut.rst.value = 0, 1
    await edge(dut)
    dut.rst.value = 0
    assert (int(dut.ready.value), int(dut.done.value)) == (1, 0), "after reset mid-division"
    await divide(dut, 45, 7, 0)
    await divide(dut, 0b100000, 0b111111, 1)
