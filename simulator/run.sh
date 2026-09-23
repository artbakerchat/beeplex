#!/usr/bin/env bash
# Run the beeplex pipeline against the simulated Bee device (no hardware,
# no login needed). Exercises the real live path: CLI auth check, list,
# per-conversation fetch, engagement scoring, and report generation.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/simulator:$PATH"
exec python3 -m beeplex.reports "$@"
