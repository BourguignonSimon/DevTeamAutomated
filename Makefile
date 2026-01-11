SHELL := /bin/bash

COMPOSE ?= docker compose

.PHONY: up down logs ps build demo demo-happy demo-failure demo-clarification demointeractive demo-clarify test lint format type-check validate pre-commit-install pre-commit validate-all

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
	./demo/demo_happy_path.sh

demo-failure:
	./demo/demo_failure_retry_dlq.sh

demo-clarification:
	./demo/demo_clarification.sh

demointeractive:
	$(COMPOSE) exec -T orchestrator sh -lc "PYTHONPATH=/app python -m demo.interactive_demo"

demo-clarify:
	$(COMPOSE) exec -T orchestrator sh -lc "PYTHONPATH=/app python demo/clarification_demo.py"

test:
	$(COMPOSE) run --rm tests

# Code quality and validation targets

lint:
	@echo "Running linters..."
	ruff check core/ services/ --output-format=github
	isort --check-only --diff core/ services/
	pylint core/ services/ --fail-under=8.0

format:
	@echo "Formatting code..."
	black core/ services/
	isort core/ services/
	ruff check core/ services/ --fix

type-check:
	@echo "Running type checker..."
	mypy core/ --ignore-missing-imports

validate-config:
	@echo "Validating configuration files..."
	@python -c "import yaml, sys; from pathlib import Path; \
	yaml_files = [f for f in Path('.').rglob('*.yml') if '.git' not in str(f)] + \
	             [f for f in Path('.').rglob('*.yaml') if '.git' not in str(f)]; \
	failed = False; \
	[print(f'✓ {f}') if not (lambda: (yaml.safe_load(open(f)), False)[1])() else print(f'✗ {f}') or setattr(sys.modules[__name__], 'failed', True) for f in yaml_files]; \
	sys.exit(1 if failed else 0)"
	@echo "Validating Docker Compose..."
	docker compose -f docker-compose.yml config --quiet
	@echo "All configuration files are valid!"

pre-commit-install:
	@echo "Installing pre-commit hooks..."
	pip install pre-commit
	pre-commit install
	@echo "Pre-commit hooks installed!"

pre-commit:
	@echo "Running pre-commit hooks..."
	pre-commit run --all-files

validate-all: lint type-check test
	@echo "All validations passed!"

validate: format lint type-check
	@echo "Code validation complete!"
