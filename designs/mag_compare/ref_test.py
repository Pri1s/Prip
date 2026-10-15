"""Hidden reference test for mag_compare: all 8192 input combinations."""

import cocotb
from cocotb.triggers import Timer


def value(v, is_signed):
    return v - 64 if is_signed and v & 0x20 else v


@cocotb.test()
async def mag_compare_matches_model(dut):
    for is_signed in (0, 1):
        for a in range(64):
            for b in range(64):
                dut.a.value = a
                dut.b.value = b
                dut.is_signed.value = is_signed
                await Timer(1, unit="ns")
                x, y = value(a, is_signed), value(b, is_signed)
                ctx = f"a={a} b={b} is_signed={is_signed}"
                assert int(dut.gt.value) == int(x > y), f"{ctx}: gt"
                assert int(dut.eq.value) == int(x == y), f"{ctx}: eq"
                assert int(dut.lt.value) == int(x < y), f"{ctx}: lt"
