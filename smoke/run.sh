#!/usr/bin/env bash
# Phase 1 acceptance check. Runs inside the container (see `make smoke`).
set -euo pipefail
cd "$(dirname "$0")"

# Runs EQY and prints its final status (PASS / FAIL / ERROR) from the DONE line.
eqy_status() {
    eqy -f "$1" -d "$2" > "$2.log" 2>&1 || true
    grep -oE 'DONE \((PASS|FAIL|ERROR|UNKNOWN)' "$2.log" | tail -1 | sed 's/DONE (//'
}

echo "== cocotb: FIFO vs queue model =="
pytest -q test_fifo.py

echo "== EQY control: fifo.v vs itself (must PASS) =="
status=$(eqy_status fifo_self.eqy eqy_out_self)
echo "status: ${status:-none}"
[ "$status" = PASS ] || { echo "FAIL: EQY could not prove a design equal to itself (see eqy_out_self.log)"; exit 1; }

echo "== EQY: fifo.v vs hand-edited fifo_bad.v (must FAIL) =="
status=$(eqy_status fifo.eqy eqy_out)
echo "status: ${status:-none}"
[ "$status" = FAIL ] || { echo "FAIL: expected EQY to reject the edit (see eqy_out.log)"; exit 1; }

echo "SMOKE PASSED"
