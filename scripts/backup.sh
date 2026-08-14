#!/usr/bin/env bash
#
# Back up everything that cannot be rebuilt: the database and the uploaded
# files. Everything else in the stack (images, indexes, embeddings) is derived
# and can be regenerated from these two.
#
#   ./scripts/backup.sh [destination]
#
# Writes <destination>/<timestamp>/ with the dump, the objects and a manifest.
# Default destination: ./backups
#
# Deliberately a script and not a cron entry: where and how often to run it is
# a deployment decision, and hiding it in a scheduler nobody reads is how a
# backup quietly stops happening. See docs/deployment/BACKUP.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

DEST="${1:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST/$STAMP"
COMPOSE=(docker compose --profile dev)

# The .env holds the credentials the containers already use; reading them here
# keeps the script from growing its own copy that can drift.
set -a && source .env && set +a

mkdir -p "$OUT"
echo "backing up into $OUT"

# --- database ------------------------------------------------------------
# Custom format (-Fc): compressed, and restorable table by table, which is
# what makes a partial recovery possible instead of all or nothing.
echo "  postgres: dumping $POSTGRES_DB"
"${COMPOSE[@]}" exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner \
  > "$OUT/postgres.dump"

# --- uploaded files ------------------------------------------------------
# The MinIO image ships mc and nothing else: no tar, no gzip, not even find.
# So mc mirrors the bucket to a path inside the container and docker copies
# that out, which needs no tooling in the image at all.
echo "  minio: mirroring bucket $MINIO_BUCKET"
"${COMPOSE[@]}" exec -T minio sh -c "
  mc alias set bk http://localhost:9000 '$MINIO_ROOT_USER' '$MINIO_ROOT_PASSWORD' >/dev/null &&
  mc mirror --quiet --overwrite bk/$MINIO_BUCKET /tmp/bk-$STAMP >/dev/null" || true
"${COMPOSE[@]}" cp "minio:/tmp/bk-$STAMP" "$OUT/minio" >/dev/null
"${COMPOSE[@]}" exec -T minio mc rm --recursive --force "/tmp/bk-$STAMP" >/dev/null 2>&1 || true

# --- manifest ------------------------------------------------------------
# What a restore needs to know before it starts: which schema version the dump
# expects, and how big the thing is. A dump restored onto a database at a
# different migration is the failure mode this line exists to prevent.
REVISION="$("${COMPOSE[@]}" exec -T api sh -c 'cd /app && alembic current 2>/dev/null' \
  | grep -oE '^[0-9a-f]{12}' | head -1 || echo unknown)"

cat > "$OUT/manifest.txt" <<MANIFEST
taken_at=$STAMP
alembic_revision=$REVISION
postgres_db=$POSTGRES_DB
minio_bucket=$MINIO_BUCKET
postgres_dump_bytes=$(stat -c%s "$OUT/postgres.dump")
minio_objects=$(find "$OUT/minio" -type f | wc -l)
minio_bytes=$(du -sb "$OUT/minio" | cut -f1)
MANIFEST

echo "done:"
sed 's/^/  /' "$OUT/manifest.txt"
