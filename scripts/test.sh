#!/usr/bin/env bash
# Run the test suite (pytest) via Docker using uv — no local Python required.
# Usage: ./scripts/test.sh [pytest args]
set -euo pipefail

UV_IMAGE="ghcr.io/astral-sh/uv:python3.13-bookworm-slim"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker run --rm -e UV_LINK_MODE=copy -v "$ROOT":/app -w /app "$UV_IMAGE" \
  uv run --frozen --extra dev pytest "$@"
