SHELL := /bin/bash

COMPOSE ?= docker compose

.PHONY: up down logs ps build demo demointeractive demo-clarify test lint help

help: ## Show available make targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z0-9_.-]+:.*##/ {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Start the docker compose stack
	$(COMPOSE) up -d --build

build: ## Build docker images
	$(COMPOSE) build

down: ## Stop and remove docker resources
	$(COMPOSE) down -v --remove-orphans

logs: ## Tail compose logs
	$(COMPOSE) logs -f --tail=200

ps: ## Show compose status
	$(COMPOSE) ps

demo: ## Run the demo event seeding flow
	$(COMPOSE) exec -T orchestrator sh -lc "python -m demo.seed_events"

demointeractive: ## Run the interactive demo flow
	$(COMPOSE) exec -T orchestrator sh -lc "PYTHONPATH=/app python -m demo.interactive_demo"

demo-clarify: ## Run the clarification demo flow
	$(COMPOSE) exec -T orchestrator sh -lc "PYTHONPATH=/app python demo/clarification_demo.py"

test: ## Run unit tests
	pytest -q -m "not integration"

lint: ## Run formatting, linting, and type checks
	ruff format --check .
	ruff check .
	mypy .
	pyright
