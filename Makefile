#################################################################################
# GLOBALS                                                                       #
#################################################################################

PROJECT_NAME = OC-Confirmez-vos-competences-en-MLOps

#################################################################################
# COMMANDS                                                                      #
#################################################################################

## Install Python Dependencies (API + dev)
.PHONY: requirements
requirements:
	uv sync --extra api

## Run the API locally with autoreload
.PHONY: run
run:
	uv run uvicorn api.main:app --reload

## Build the API Docker image
.PHONY: docker-build
docker-build:
	docker compose build

## Build, migrate, then run the full local Docker stack
.PHONY: docker-run
docker-run:
	docker compose build
	docker compose run --rm api alembic upgrade head
	docker compose up -d

## Stop the local Docker Compose stack
.PHONY: docker-down
docker-down:
	docker compose down

## Re-apply migrations without restarting an already-running stack
.PHONY: db-migrate
db-migrate:
	uv run alembic upgrade head

## Delete all compiled Python files
.PHONY: clean
clean:
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -delete

## Lint using ruff (check only)
.PHONY: lint
lint:
	uv run ruff check .
	uv run ruff format --check .

## Format source code with ruff
.PHONY: format
format:
	uv run ruff check --fix .
	uv run ruff format .

## Run tests (if pytest is installed)
.PHONY: test
test:
	uv run pytest

## Set up Python interpreter environment
.PHONY: create-environment
create-environment:
	uv venv
	@echo ">>> New uv virtual environment created. Activate with:"
	@echo ">>> Windows: .\\.venv\\Scripts\\activate"
	@echo ">>> Unix/macOS: source ./.venv/bin/activate"

#################################################################################
# PROJECT RULES                                                                 #
#################################################################################

## Git Hooks
.PHONY: setup-hooks
setup-hooks:
	uv run pre-commit install
	uv run pre-commit install --hook-type pre-push

#################################################################################
# DATA DRIFT ANALYSIS                                                          #
#################################################################################

## Install drift analysis tooling (Evidently, k6 fixtures, notebook)
.PHONY: drift-requirements
drift-requirements:
	uv sync --extra api --group drift

## Export prediction_events to a local Parquet file
.PHONY: export-drift-tracking
export-drift-tracking:
	uv run python scripts/export_tracking_for_drift.py

## Download the drift reference dataset from the private HF bucket
.PHONY: download-drift-reference
download-drift-reference:
	uv run python scripts/download_drift_reference.py

## Generate the k6 ramped drift fixture from the downloaded reference
.PHONY: generate-drift-fixtures
generate-drift-fixtures:
	uv run python scripts/generate_drift_fixtures.py

#################################################################################
# Self Documenting Commands                                                     #
#################################################################################

.DEFAULT_GOAL := help

define PRINT_HELP_PYSCRIPT
import re, sys; \
lines = '\n'.join([line for line in sys.stdin]); \
matches = re.findall(r'\n## (.*)\n[\s\S]+?\n([a-zA-Z_-]+):', lines); \
print('Available rules:\n'); \
print('\n'.join(['{:25}{}'.format(*reversed(match)) for match in matches]))
endef
export PRINT_HELP_PYSCRIPT

help:
	@uv run python -c "${PRINT_HELP_PYSCRIPT}" < $(MAKEFILE_LIST)
