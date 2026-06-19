PYTHON := python
PIP := pip

.PHONY: setup format lint test run-api run-backfill run-sync run-leiden up down

setup:
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

format:
	$(PYTHON) -m black app tests scripts
	$(PYTHON) -m ruff check app tests scripts --fix

lint:
	$(PYTHON) -m black --check app tests scripts
	$(PYTHON) -m ruff check app tests scripts
	$(PYTHON) -m mypy app

test:
	$(PYTHON) -m pytest

run-api:
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

run-backfill:
	$(PYTHON) scripts/run_full_backfill.py

run-sync:
	$(PYTHON) scripts/run_incremental_sync.py

run-leiden:
	$(PYTHON) scripts/run_leiden.py

up:
	docker compose up -d

down:
	docker compose down