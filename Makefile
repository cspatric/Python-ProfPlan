.PHONY: up down logs ps lint format test test-integration coverage migrate revision pull-model certs

# Start the full stack (core + observability) and rebuild images.
up:
	docker compose --profile dev --profile observability up -d --build

# Generate a self-signed TLS cert for Traefik's local HTTPS listener (run
# once; regenerate any time with the same command). Swap for a real
# Let's Encrypt cert in production — see docker/traefik/traefik.yml.
certs:
	mkdir -p docker/traefik/certs
	openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
		-keyout docker/traefik/certs/local.key \
		-out docker/traefik/certs/local.crt \
		-subj "/CN=api.localhost" \
		-addext "subjectAltName=DNS:api.localhost,DNS:localhost"

# Stop everything (volumes/data are kept).
down:
	docker compose --profile dev --profile observability down

logs:
	docker compose logs -f api worker

ps:
	docker compose --profile dev --profile observability ps

lint:
	./scripts/lint.sh

format:
	./scripts/format.sh

# Unit tests.
test:
	./scripts/test.sh

# Integration tests (real Postgres + Redis).
test-integration:
	./scripts/test-integration.sh

# Unit tests with a coverage report.
coverage:
	./scripts/coverage.sh

# Apply database migrations.
migrate:
	docker compose exec api alembic upgrade head

# Autogenerate a migration: make revision m="add something"
revision:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

# Pull the embedding model into Ollama (run once).
pull-model:
	docker compose exec ollama ollama pull bge-m3
