#!/bin/bash
# A read-only role for Grafana.
#
# The cost dashboard reads per-account spend straight from the database,
# because a per-user label on a Prometheus counter is an unbounded number of
# time series and the first thing it breaks is Prometheus. Reading is all it
# ever needs to do, so it gets a role that can do nothing else: a dashboard
# with the application's own credentials is one bad panel away from a DELETE.
#
# Runs only when the data directory is created, like every script in
# docker-entrypoint-initdb.d. For a database that already exists, the same
# statements are in docs/observability/LLM-COST.md.
set -e

if [ -z "$GRAFANA_DB_PASSWORD" ]; then
    echo "GRAFANA_DB_PASSWORD not set: skipping the read-only Grafana role"
    exit 0
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
    CREATE ROLE grafana_ro LOGIN PASSWORD '${GRAFANA_DB_PASSWORD}';
    GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO grafana_ro;
    GRANT USAGE ON SCHEMA public TO grafana_ro;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_ro;
    -- Tables created later (a migration) are covered too, otherwise the
    -- dashboard breaks on the next release for no visible reason.
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_ro;
SQL
