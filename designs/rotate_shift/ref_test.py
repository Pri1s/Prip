"""Hidden reference test for rotate_shift: all 8192 input combinations."""

import cocotb
from cocotb.triggers import Timer


def model(d, amt, left, rot):
    if rot:
        if left:
            return ((d << amt) | (d >> (8 - amt))) & 0xFF
        return ((d >> amt) | (d << (8 - amt))) & 0xFF
    return (d << amt) & 0xFF if left else d >> amt


@cocotb.test()
async def rotate_shift_matches_model(dut):
    for left in (0, 1):
        for rot in (0, 1):
            for amt in range(8):
                for d in range(256):
                    dut.d.value = d
                    dut.amt.value = amt
                    dut.left.value = left
                    dut.rot.value = rot
                    await Timer(1, unit="ns")
                    q = model(d, amt, left, rot)
                    assert int(dut.q.value) == q, f"d={d:#04x} amt={amt} left={left} rot={rot}: q"
