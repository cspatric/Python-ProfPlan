.PHONY: up down logs ps lint format test test-integration coverage migrate revision pull-model

# Start the full stack (core + observability) and rebuild images.
up:
	docker compose --profile dev --profile observability up -d --build

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
