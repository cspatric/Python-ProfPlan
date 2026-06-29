#!/usr/bin/env bash
# Run Ruff formatter via Docker. Pass --check to verify without writing.
# Usage: ./scripts/format.sh [--check]
set -euo pipefail

RUFF_IMAGE="ghcr.io/astral-sh/ruff:0.9.6"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker run --rm -v "$ROOT":/io -w /io "$RUFF_IMAGE" format "$@" .
