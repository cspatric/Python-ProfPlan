#!/usr/bin/env bash
#
# Restore a backup taken by scripts/backup.sh.
#
#   ./scripts/restore.sh backups/20260814T031500Z
#
# This DESTROYS the current database and bucket contents and replaces them
# with the backup's. It asks first unless RESTORE_YES=1 is set, which is what
# the drill in docs/deployment/BACKUP.md uses.
#
# A backup nobody has restored is a hypothesis. Run this against a throwaway
# stack on a schedule; the doc records how long it took the last time.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

SRC="${1:?usage: restore.sh <backup directory>}"
[ -f "$SRC/postgres.dump" ] || { echo "no postgres.dump in $SRC"; exit 1; }
[ -d "$SRC/minio" ] || { echo "no minio directory in $SRC"; exit 1; }

COMPOSE=(docker compose --profile dev)
set -a && source .env && set +a

echo "restoring from $SRC"
sed 's/^/  /' "$SRC/manifest.txt" 2>/dev/null || true

if [ "${RESTORE_YES:-0}" != "1" ]; then
  read -r -p "This replaces the current database and bucket. Continue? [y/N] " reply
  [ "$reply" = "y" ] || { echo "aborted"; exit 1; }
fi

START=$(date +%s)

# --- database ------------------------------------------------------------
# The workers are stopped first: a task writing during a restore would race
# with it and leave rows the dump never had.
echo "  stopping api and worker"
"${COMPOSE[@]}" stop api worker >/dev/null

echo "  postgres: recreating $POSTGRES_DB"
"${COMPOSE[@]}" exec -T postgres psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL >/dev/null
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
 WHERE datname = '$POSTGRES_DB' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "$POSTGRES_DB";
CREATE DATABASE "$POSTGRES_DB" OWNER "$POSTGRES_USER";
SQL

# pg_restore reports harmless notices about extensions it cannot recreate as
# owner; --exit-on-error would abort on those, so the exit code is checked by
# the verification below instead.
"${COMPOSE[@]}" exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner < "$SRC/postgres.dump" \
  2>/dev/null || true

# --- uploaded files ------------------------------------------------------
# Mirrored back with --remove, so a file deleted after the backup is gone
# again afterwards: a restore has to reproduce the moment, not merge into it.
echo "  minio: restoring bucket $MINIO_BUCKET"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
"${COMPOSE[@]}" exec -T minio mc rm --recursive --force "/tmp/rs-$STAMP" >/dev/null 2>&1 || true
"${COMPOSE[@]}" cp "$SRC/minio" "minio:/tmp/rs-$STAMP" >/dev/null
"${COMPOSE[@]}" exec -T minio sh -c "
  mc alias set rs http://localhost:9000 '$MINIO_ROOT_USER' '$MINIO_ROOT_PASSWORD' >/dev/null &&
  mc mb --ignore-existing rs/$MINIO_BUCKET >/dev/null &&
  mc mirror --quiet --overwrite --remove /tmp/rs-$STAMP rs/$MINIO_BUCKET >/dev/null &&
  mc rm --recursive --force /tmp/rs-$STAMP >/dev/null"

echo "  starting api and worker"
"${COMPOSE[@]}" start api worker >/dev/null

# --- verification --------------------------------------------------------
# A restore that "worked" and left an empty database is the failure this
# refuses to report as success.
echo "  verifying"
"${COMPOSE[@]}" exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "
  SELECT 'users=' || (SELECT count(*) FROM users)
      || ' subjects=' || (SELECT count(*) FROM subjects)
      || ' plans=' || (SELECT count(*) FROM plans)
      || ' documents=' || (SELECT count(*) FROM document)
      || ' chunks=' || (SELECT count(*) FROM chunks);" | sed 's/^/    /'

"${COMPOSE[@]}" exec -T minio sh -c "
  mc alias set rs http://localhost:9000 '$MINIO_ROOT_USER' '$MINIO_ROOT_PASSWORD' >/dev/null &&
  mc ls --recursive rs/$MINIO_BUCKET | wc -l" | sed 's/^/    objects=/'

echo "restored in $(( $(date +%s) - START ))s"
