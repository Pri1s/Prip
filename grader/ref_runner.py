"""Runs a design's hidden reference test (designs/<name>/ref_test.py) against any RTL file.

Used by the corpus check on golden RTL now, and by the grader on submitted patches later.
"""

import json
import sys
from pathlib import Path

from cocotb_tools.runner import get_results, get_runner


def run_reference(design_dir: Path, rtl: Path, build_dir: Path) -> tuple[int, int]:
    """Returns (tests run, tests failed). A simulator crash counts as all tests failing."""
    design_dir, rtl, build_dir = Path(design_dir).resolve(), Path(rtl).resolve(), Path(build_dir).resolve()
    top = json.loads((design_dir / "meta.json").read_text())["top"]
    runner = get_runner("icarus")
    runner.build(
        sources=[rtl],
        hdl_toplevel=top,
        build_dir=build_dir,
        timescale=("1ns", "1ps"),
        always=True,
    )
    # The runner hands sys.path to the simulator as PYTHONPATH, so this is how it finds
    # ref_test.py. Every design's test has the same module name, so remove it afterwards.
    sys.path.insert(0, str(design_dir))
    try:
        results = runner.test(
            hdl_toplevel=top,
            test_module="ref_test",
            build_dir=build_dir,
            test_dir=build_dir,
            results_xml=str(build_dir / "results.xml"),
        )
        return get_results(results)
    except (SystemExit, RuntimeError):
        return (1, 1)
    finally:
        sys.path.remove(str(design_dir))
