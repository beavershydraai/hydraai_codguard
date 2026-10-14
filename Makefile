# Local development. Run `make help` for the list of targets.
#
# make dev            backend :8080 + Prism mock :4010 + frontend :5173 (frontend calls the mock)
# make dev API=backend   backend + frontend, with the frontend calling the local backend

API ?= mock

BACKEND_PORT ?= 8080
MOCK_PORT ?= 4010
FRONTEND_PORT ?= 5173

# The backend reads .env at the repo root when it exists (copy it from .env.example).
ENV_FILE := $(if $(wildcard .env),--env-file ../.env,)

ifeq ($(API),backend)
API_PROXY_TARGET := http://127.0.0.1:$(BACKEND_PORT)
else ifeq ($(API),mock)
API_PROXY_TARGET := http://127.0.0.1:$(MOCK_PORT)
else
$(error API must be "mock" or "backend", got "$(API)")
endif

# Prefixes every line of a process's output with its name, flushing each line.
label = awk '{ print "[$(1)] " $$0; fflush() }'

.PHONY: help install dev dev-backend dev-frontend mock test lint generate

help: ## Show this help
	@awk 'BEGIN { FS = ":.*## " } /^[a-z-]+:.*## / { printf "  %-14s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Install backend and frontend dependencies
	cd backend && uv sync
	cd frontend && pnpm install

dev: ## Run the dev servers together (API=mock|backend); Ctrl-C stops all
	@[ -f .env ] || echo "note: no .env at the repo root, so backend sign-in is disabled (cp .env.example .env)"
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) --no-print-directory dev-backend 2>&1 | $(call label,api) & \
	$(if $(filter mock,$(API)),$(MAKE) --no-print-directory mock 2>&1 | $(call label,mock) &,) \
	$(MAKE) --no-print-directory dev-frontend 2>&1 | $(call label,web) & \
	wait

dev-backend: ## Backend only, with reload (http://localhost:8080/docs)
	cd backend && uv run $(ENV_FILE) uvicorn app.main:app --reload --port $(BACKEND_PORT)

dev-frontend: ## Frontend only; /api goes to API_PROXY_TARGET
	cd frontend && API_PROXY_TARGET=$(API_PROXY_TARGET) pnpm dev --port $(FRONTEND_PORT)

mock: ## Prism mock server answering with the contract's examples
	cd frontend && pnpm mock --port $(MOCK_PORT)

test: ## Backend and frontend tests
	cd backend && uv run pytest -q
	cd frontend && pnpm test

lint: ## Lint and format checks, as in CI
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && pnpm lint && pnpm format:check && pnpm typecheck

generate: ## Export the API contract and regenerate the frontend client
	cd backend && uv run python -m app.openapi_export
	cd frontend && pnpm generate:api
