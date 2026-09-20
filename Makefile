.DEFAULT_GOAL := help
SHELL := /bin/bash

VENV    ?= .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
PORT    ?= 8000
IMAGE   ?= student-engagement-api:local

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/activate:
	python3.12 -m venv $(VENV)
	$(PIP) install --upgrade pip

.PHONY: install
install: $(VENV)/bin/activate ## Create the venv and install runtime + dev dependencies
	$(PIP) install -r requirements-dev.txt

.PHONY: run
run: ## Run the API with reload on http://localhost:$(PORT)
	$(VENV)/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port $(PORT)

.PHONY: seed
seed: ## Seed deterministic demo data (add ARGS="--reset")
	$(PY) -m scripts.seed $(ARGS)

.PHONY: lint
lint: ## ruff check + format check
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

.PHONY: format
format: ## Apply ruff formatting and safe fixes
	$(VENV)/bin/ruff check --fix .
	$(VENV)/bin/ruff format .

.PHONY: typecheck
typecheck: ## mypy --strict
	$(VENV)/bin/mypy

.PHONY: test
test: ## Run the test suite with coverage
	$(PY) -m pytest --cov --cov-report=term-missing --cov-report=xml

.PHONY: security
security: ## bandit (code) + pip-audit (dependencies)
	$(VENV)/bin/bandit -c pyproject.toml -r app scripts -q
	$(VENV)/bin/pip-audit -r requirements.txt --strict

.PHONY: check
check: lint typecheck test security ## Everything CI runs

.PHONY: docker-build
docker-build: ## Build the container image
	docker build -t $(IMAGE) .

.PHONY: docker-run
docker-run: ## Run the container on http://localhost:$(PORT)
	docker run --rm -p $(PORT):8000 $(IMAGE)

.PHONY: up
up: ## docker compose up (SQLite)
	docker compose up --build

.PHONY: up-postgres
up-postgres: ## docker compose up with the Postgres profile
	docker compose --profile postgres up --build

.PHONY: down
down: ## Stop compose and remove volumes
	docker compose --profile postgres down -v

.PHONY: clean
clean: ## Remove caches, coverage output and the demo database
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -f engagement.db
