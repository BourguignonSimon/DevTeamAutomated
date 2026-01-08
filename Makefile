SHELL := /bin/bash

COMPOSE ?= docker compose

.PHONY: up down logs ps build demo demointeractive demo-clarify test lint help

up:
	$(COMPOSE) up -d --build

build:
	$(COMPOSE) build

down:
	$(COMPOSE) down -v --remove-orphans

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

demo:
	$(COMPOSE) exec -T orchestrator sh -lc "python -m demo.seed_events"

demointeractive:
	$(COMPOSE) exec -T orchestrator sh -lc "PYTHONPATH=/app python -m demo.interactive_demo"

demo-clarify:
	$(COMPOSE) exec -T orchestrator sh -lc "PYTHONPATH=/app python demo/clarification_demo.py"

test:
	$(COMPOSE) run --rm tests

lint:
	python -m ruff check .
	python -m ruff format --check .

help:
	@echo "Available targets:"
	@echo "  make up      - Build and start the Docker Compose stack"
	@echo "  make down    - Stop and remove the Docker Compose stack"
	@echo "  make build   - Build Docker images"
	@echo "  make logs    - Tail Docker Compose logs"
	@echo "  make ps      - List Docker Compose services"
	@echo "  make demo    - Seed demo events via the orchestrator container"
	@echo "  make test    - Run the test suite container"
	@echo "  make lint    - Run ruff lint and format checks"
