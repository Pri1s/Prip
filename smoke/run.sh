#!/usr/bin/env bash
# Phase 1 acceptance check. Runs inside the container (see `make smoke`).
set -euo pipefail
cd "$(dirname "$0")"

# Grades a FIFO variant against fifo.v and prints the verdict (PASS / FAIL / INCONCLUSIVE / ERROR).
grade() {
    python -m grader.equiv --gold fifo.v --meta meta.json --gate "$1" --work "../build/smoke/$2" --no-eqy \
        > "../build/smoke/$2.log" 2>&1 || true
    head -1 "../build/smoke/$2.log" | cut -d: -f1
}

# Checks that variant $1 gets verdict $2 from the grader.
expect() {
    local status
    status=$(grade "$1" "${1%.v}")
    echo "$1: ${status:-none} (expected $2)"
    [ "$status" = "$2" ] || { echo "FAIL: see build/smoke/${1%.v}.log"; exit 1; }
}

mkdir -p ../build/smoke
export PYTHONPATH="$PWD/.."

echo "== cocotb: FIFO vs queue model =="
pytest -q test_fifo.py

echo "== grader control: fifo.v vs itself (must PASS) =="
expect fifo.v PASS

echo "== grader: hand-edited variants (must FAIL) =="
expect fifo_bad.v FAIL
expect fifo_data_bad.v FAIL

echo "SMOKE PASSED"
