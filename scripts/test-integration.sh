#!/usr/bin/env bash
# Run the INTEGRATION test suite against real Postgres/Redis on the stack
# network, using a throwaway test database. Requires the stack services to be
# available (they are started as dependencies).
# Usage: ./scripts/test-integration.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# `dev` is needed so the postgres/redis dependencies are defined; `run` only
# starts those dependencies, not the rest of the dev stack.
docker compose --profile tools --profile dev run --rm test
