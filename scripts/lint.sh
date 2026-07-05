#!/usr/bin/env bash
# Run Ruff lint + format check via Docker — mirrors exactly what CI enforces
# (ruff check + ruff format --check).
# Usage:
#   ./scripts/lint.sh          # check only (fails on lint or format issues)
#   ./scripts/lint.sh --fix    # auto-fix lint issues and reformat files
set -euo pipefail

RUFF_IMAGE="ghcr.io/astral-sh/ruff:0.9.6"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
run() { docker run --rm -v "$ROOT":/io -w /io "$RUFF_IMAGE" "$@"; }

if [[ "${1:-}" == "--fix" ]]; then
    run check --fix .
    run format .
else
    run check .
    run format --check .
fi
