#!/usr/bin/env bash
# Run the ProfPlan load test (AI-free) against a running dev stack.
#
# Uses the official Locust image on the compose backend network and targets the
# API container directly (http://api:8000), so no host install of Locust is
# needed. Results (CSV + HTML) are written to perf/results/.
#
# Usage:
#   perf/run.sh                 # defaults: 100 users, spawn 20/s, 60s
#   USERS=300 RATE=50 TIME=120s perf/run.sh
set -euo pipefail

USERS="${USERS:-100}"
RATE="${RATE:-20}"
TIME="${TIME:-60s}"
TARGET="${TARGET:-http://api:8000}"

here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$here/results"

# Detect the compose backend network (project prefix varies by directory name).
network="$(docker network ls --format '{{.Name}}' | grep -E '(^|_)backend$' | head -1)"
if [ -z "$network" ]; then
  echo "ERROR: could not find the compose 'backend' network. Is the stack up?" >&2
  exit 1
fi

echo "Load test -> $TARGET | users=$USERS spawn=$RATE/s time=$TIME | network=$network"
stamp="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo run)"

docker run --rm --network "$network" \
  -v "$here:/mnt/locust" \
  locustio/locust \
  -f /mnt/locust/locustfile.py \
  --headless \
  --host "$TARGET" \
  -u "$USERS" -r "$RATE" -t "$TIME" \
  --csv "/mnt/locust/results/$stamp" \
  --html "/mnt/locust/results/$stamp.html" \
  --only-summary

echo "Done. Summary CSV: perf/results/$stamp""_stats.csv"
