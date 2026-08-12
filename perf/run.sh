#!/usr/bin/env bash
# Run the ProfPlan load test (AI-free) against a running dev stack.
#
# Uses the official Locust image on the compose backend network and targets the
# API container directly (http://api:8000), so no host install of Locust is
# needed. Results (CSV + HTML) are written to perf/results/.
#
# Usage:
#   perf/run.sh                          # flat: 100 users, spawn 20/s, 60s
#   USERS=300 RATE=50 TIME=120s perf/run.sh
#
#   # capacity discovery — ramp until the SLO breaks, report the ceiling:
#   SHAPE=step perf/run.sh
#   SHAPE=step STEP_START=50 STEP_USERS=50 STEP_MAX=600 perf/run.sh
#
#   # measure argon2/auth throughput on purpose:
#   AUTH_WEIGHT=3 perf/run.sh
#
# No LLM is ever called: token-spending paths are blocked in locustfile.py.
set -euo pipefail

USERS="${USERS:-100}"
RATE="${RATE:-20}"
TIME="${TIME:-60s}"
TARGET="${TARGET:-http://api:8000}"
SHAPE="${SHAPE:-flat}"

here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$here/results"

# The daemon may live on a non-active context (e.g. Docker Desktop is selected
# but the system daemon is the one running the stack). Prefer whatever context
# actually answers, so the script works on both.
if ! docker info >/dev/null 2>&1; then
  if DOCKER_HOST=unix:///var/run/docker.sock docker info >/dev/null 2>&1; then
    export DOCKER_HOST=unix:///var/run/docker.sock
    echo "note: active docker context is unreachable; using $DOCKER_HOST"
  else
    echo "ERROR: cannot reach a docker daemon. Is Docker running?" >&2
    exit 1
  fi
fi

# Detect the compose backend network (project prefix varies by directory name).
network="$(docker network ls --format '{{.Name}}' | grep -E '(^|_)backend$' | head -1)"
if [ -z "$network" ]; then
  echo "ERROR: could not find the compose 'backend' network. Is the stack up?" >&2
  echo "       docker compose --profile dev up -d" >&2
  exit 1
fi

# Seed a realistic dataset and capture the logged-in sessions. Runs inside the
# api container (it already has the DB creds + drivers). stdout is the pool
# JSON; progress goes to stderr.
if [ "${SEED:-1}" = "1" ]; then
  echo "Seeding dataset (accounts + subjects + plans; no AI involved) ..."
  ACCOUNTS="${ACCOUNTS:-20}" \
  docker compose -f "$here/../docker-compose.yml" exec -T \
    -e ACCOUNTS="${ACCOUNTS:-20}" \
    -e SUBJECTS_PER_ACCOUNT="${SUBJECTS_PER_ACCOUNT:-60}" \
    -e PLANS_PER_ACCOUNT="${PLANS_PER_ACCOUNT:-60}" \
    api python - < "$here/seed.py" > "$here/results/.pool.json"
else
  echo "SEED=0 -> reusing existing perf/results/.pool.json"
fi

# E2E mode (MOCK_LLM=1): before unlocking POST /plans, PROVE the LLM traffic
# lands on the mock. The canary creates one probe plan and checks the mock's
# hit counter moved; only then is MOCK_VERIFIED=1 handed to locust.
MOCK_VERIFIED=0
if [ "${MOCK_LLM:-0}" = "1" ]; then
  echo "E2E mode: verifying the mock LLM canary ..."
  docker run --rm --network "$network" -v "$here:/mnt/locust" \
    --entrypoint python locustio/locust /mnt/locust/canary.py
  MOCK_VERIFIED=1
  echo "Canary verified — plan-generation traffic unlocked (PLAN_WEIGHT=${PLAN_WEIGHT:-0})."
fi

if [ "$SHAPE" = "step" ]; then
  echo "Capacity run -> $TARGET | steps of ${STEP_USERS:-25} users every ${STEP_TIME:-30}s (max ${STEP_MAX:-500}) | network=$network"
else
  echo "Load test -> $TARGET | users=$USERS spawn=$RATE/s time=$TIME | network=$network"
fi
stamp="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo run)"

# A step run ends when the shape says so, so -t must not cut it short; give it a
# generous cap derived from the ramp.
if [ "$SHAPE" = "step" ]; then
  TIME="${STEP_TIMEOUT:-3600s}"
fi

docker run --rm --network "$network" \
  -e SHAPE="$SHAPE" \
  -e STEP_START="${STEP_START:-25}" \
  -e STEP_USERS="${STEP_USERS:-25}" \
  -e STEP_TIME="${STEP_TIME:-30}" \
  -e STEP_MAX="${STEP_MAX:-500}" \
  -e STEP_SPAWN="${STEP_SPAWN:-25}" \
  -e SETTLE_SECONDS="${SETTLE_SECONDS:-20}" \
  -e WARMUP_SECONDS="${WARMUP_SECONDS:-60}" \
  -e SLO_P95_MS="${SLO_P95_MS:-1000}" \
  -e SLO_FAIL_PCT="${SLO_FAIL_PCT:-1.0}" \
  -e ACCOUNTS="${ACCOUNTS:-20}" \
  -e AUTH_WEIGHT="${AUTH_WEIGHT:-0}" \
  -e UNIQUE_IPS="${UNIQUE_IPS:-1}" \
  -e THINK_TIME_MIN="${THINK_TIME_MIN:-0.05}" \
  -e THINK_TIME_MAX="${THINK_TIME_MAX:-0.2}" \
  -e MOCK_LLM="${MOCK_LLM:-0}" \
  -e MOCK_VERIFIED="$MOCK_VERIFIED" \
  -e PLAN_WEIGHT="${PLAN_WEIGHT:-0}" \
  -e REQUEST_TARGET="${REQUEST_TARGET:-0}" \
  -v "$here:/mnt/locust" \
  locustio/locust \
  -f /mnt/locust/locustfile.py \
  --headless \
  --host "$TARGET" \
  -u "$USERS" -r "$RATE" -t "$TIME" \
  ${PROCESSES:+--processes "$PROCESSES"} \
  --csv "/mnt/locust/results/$stamp" \
  --html "/mnt/locust/results/$stamp.html" \
  --only-summary

echo "Done. Summary CSV: perf/results/$stamp""_stats.csv"
