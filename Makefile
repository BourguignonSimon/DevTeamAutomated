SHELL := /bin/bash

COMPOSE ?= docker compose

.PHONY: up down logs ps build demo demointeractive demo-clarify test

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
