#!/usr/bin/env bash
# Run the unit test suite with a coverage report, via Docker/uv.
# Usage: ./scripts/coverage.sh
set -euo pipefail

UV_IMAGE="ghcr.io/astral-sh/uv:python3.13-bookworm-slim"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker run --rm -e UV_LINK_MODE=copy -v "$ROOT":/app -w /app "$UV_IMAGE" \
  uv run --frozen --extra dev pytest -m "not integration" \
  --cov=app --cov-report=term-missing
