# PB Platform — canonical developer entry points.
# Every target here is also what CI runs; keep them in sync.

.DEFAULT_GOAL := help

API_DIR := apps/api
WEB_DIR := apps/web

.PHONY: help setup setup-api setup-web dev-api dev-web migrate lint lint-api lint-web \
	format format-api format-web format-check typecheck typecheck-api typecheck-web \
	test test-api test-web test-e2e build openapi up down logs ps compose-config

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# --- Setup -------------------------------------------------------------------

setup: setup-api setup-web ## Install all dependencies (API + web)

setup-api: ## Install backend dependencies into apps/api/.venv
	cd $(API_DIR) && uv sync --all-groups

setup-web: ## Install frontend workspace dependencies
	pnpm install

# --- Development -------------------------------------------------------------

dev-api: ## Run the API with auto-reload on :8000
	cd $(API_DIR) && uv run uvicorn pb_api.main:app --reload --host 0.0.0.0 --port 8000

dev-web: ## Run the web app on :3000
	pnpm --filter @pb/web dev

migrate: ## Apply database migrations
	cd $(API_DIR) && uv run alembic upgrade head

openapi: ## Export the OpenAPI spec to shared/openapi/openapi.json
	cd $(API_DIR) && uv run python ../../scripts/export_openapi.py

# --- Quality -----------------------------------------------------------------

lint: lint-api lint-web ## Lint everything

lint-api: ## Ruff lint + Black check + import hygiene
	cd $(API_DIR) && uv run ruff check . && uv run black --check .

lint-web: ## ESLint across JS/TS workspaces
	pnpm -r --if-present lint

format: format-api format-web ## Auto-format everything

format-api:
	cd $(API_DIR) && uv run ruff check --fix . && uv run black .

format-web:
	pnpm run format

format-check: ## Verify formatting without writing
	cd $(API_DIR) && uv run black --check .
	pnpm run format:check

typecheck: typecheck-api typecheck-web ## Static type checks

typecheck-api:
	cd $(API_DIR) && uv run mypy src tests

typecheck-web:
	pnpm -r --if-present typecheck

# --- Tests -------------------------------------------------------------------

test: test-api test-web ## Unit/integration tests (API + web)

test-api: ## Pytest suite
	cd $(API_DIR) && uv run pytest

test-web: ## Vitest suites
	pnpm -r --if-present test

test-e2e: ## Playwright end-to-end suite (boots api + web)
	pnpm --filter @pb/e2e run e2e

build: ## Production builds of all JS/TS workspaces
	pnpm -r --if-present build

# --- Docker ------------------------------------------------------------------

up: ## Start the full stack (traefik, api, web, postgres, redis)
	docker compose up -d --build

down: ## Stop the stack
	docker compose down

logs: ## Tail stack logs
	docker compose logs -f --tail=100

ps: ## Show stack status
	docker compose ps

compose-config: ## Validate docker-compose configuration
	docker compose config --quiet && echo "compose config OK"
