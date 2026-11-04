#!/usr/bin/env bash
# One-command entry for the offline research pipeline.
# Usage:
#   ./run_research.sh verify                  # 6 offline check suites
#   ./run_research.sh replay                  # deterministic replay of the example mission
#   ./run_research.sh benchmark [episodes] [seed_start] [output_dir]
# Set RISKWEAVE_PYTHON to a Python 3.10+ executable to override the interpreter.
set -euo pipefail
cd "$(dirname "$0")"

PY="${RISKWEAVE_PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python
MODE="${1:-verify}"

case "$MODE" in
  verify)
    for script in tools/verify_workspace.py tools/check_runtime_storage.py \
                  tools/check_selective_replanning.py tools/check_fortress_overlay.py \
                  tools/check_randomized_invariants.py tools/check_simulation_resources.py; do
      "$PY" -B "$script"
    done
    ;;
  replay)
    "$PY" -B tools/run_selective_replay.py
    ;;
  benchmark)
    EPISODES="${2:-50}"
    SEED_START="${3:-1000}"
    OUTPUT="${4:-artifacts/benchmark-$(date +%s)}"
    "$PY" -B tools/run_selective_benchmark.py --episodes "$EPISODES" --seed-start "$SEED_START" --output "$OUTPUT"
    ;;
  *)
    echo "Unknown mode: $MODE (expected verify | replay | benchmark)" >&2
    exit 2
    ;;
esac
