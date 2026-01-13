SHELL := /bin/bash

COMPOSE ?= docker compose

.PHONY: up down logs ps build demo demo-happy demo-failure demo-clarification demointeractive demo-clarify test

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

demo: demo-happy demo-failure demo-clarification

demo-happy:
	bash ./demo/demo_happy_path.sh

demo-failure:
	bash ./demo/demo_failure_retry_dlq.sh

demo-clarification:
	bash ./demo/demo_clarification.sh

demointeractive:
	$(COMPOSE) exec -T orchestrator sh -lc "PYTHONPATH=/app python -m demo.interactive_demo"

demo-clarify:
	$(COMPOSE) exec -T orchestrator sh -lc "PYTHONPATH=/app python demo/clarification_demo.py"

test:
	$(COMPOSE) run --rm tests
