# lenta-mvp — local dev cockpit.
# Quickstart:  make up && make seed && make demo   then open http://localhost:8080
.DEFAULT_GOAL := help
SHELL := /bin/bash

# Load .env if present so CLI targets (seed/test) see the same config.
ifneq (,$(wildcard .env))
include .env
export
endif

.PHONY: help up down restart logs ps build seed demo reset \
        api trainer dashboard test fmt lint sync smoke deploy-help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Start postgres + redis + all services (docker-compose)
	docker compose up -d --build
	@echo "API   -> http://localhost:8000/health"
	@echo "Dash  -> http://localhost:8080"

down: ## Stop all services
	docker compose down

restart: ## Restart all services
	docker compose restart

reset: ## Stop and wipe the database volume (clean slate)
	docker compose down -v

logs: ## Tail logs from all services
	docker compose logs -f --tail=120

ps: ## Show running services
	docker compose ps

build: ## Rebuild all images
	docker compose build

seed: ## Seed catalog/users/backfill + train v1 (runs inside trainer)
	docker compose run --rm trainer python -m trainer.seed

demo: ## Seed a clean, compelling starting state for a live demo
	docker compose run --rm trainer python -m trainer.seed --demo
	@echo "Demo state ready. Open http://localhost:8080 and use Scenario Controls."

# ---- Local (non-docker) dev: requires `make sync` + running postgres/redis ----
sync: ## Create the uv dev venv with all workspace members
	uv sync

api: ## Run the api locally (needs DATABASE_URL/REDIS_URL + uv sync)
	uv run uvicorn api.main:app --host $${API_HOST:-0.0.0.0} --port $${PORT:-8000} --reload

trainer: ## Run the trainer locally
	uv run python -m trainer.main

dashboard: ## Run the dashboard dev server (Vite)
	cd services/dashboard && npm install && npm run dev

test: ## Run the python test suite
	uv run pytest

smoke: ## End-to-end smoke: seed + train + recommend (needs db/redis)
	uv run python -m lenta_core.cli smoke

fmt: ## Format + autofix with ruff
	uv run ruff format . && uv run ruff check --fix .

lint: ## Lint with ruff
	uv run ruff check .

deploy-help: ## Print the Railway deploy checklist
	@sed -n '/## Railway deploy/,/## End Railway deploy/p' README.md || \
		echo "See the 'Deploy to Railway' section in README.md"
