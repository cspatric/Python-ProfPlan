#!/usr/bin/env bash
# Run Ruff lint (PEP 8 + import sorting + bugbear, etc.) via Docker.
# Usage: ./scripts/lint.sh [--fix]
set -euo pipefail

RUFF_IMAGE="ghcr.io/astral-sh/ruff:0.9.6"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker run --rm -v "$ROOT":/io -w /io "$RUFF_IMAGE" check "$@" .
