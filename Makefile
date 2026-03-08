.PHONY: install dev test test-regression test-slow test-all lint typecheck check \
        format copy-data verify-data fetch-data ingest docker-up docker-logs docker-down

install:
	uv sync --all-extras
	uv run pre-commit install

dev:
	uv run uvicorn webapp.main:app --reload --port 8080

test:
	uv run pytest tests/unit/ tests/integration/ -v

test-regression:
	uv run pytest tests/regression/ -v
	# HARD GATE: ema_rsi MNQ 15m OOS PF must be within 5% of 2.405

test-slow:
	uv run pytest -m slow -v

test-all:
	uv run pytest tests/ -v

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

format:
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

typecheck:
	uv run pyright src/

check: lint typecheck test

copy-data:
	bash scripts/copy_data.sh

verify-data:
	uv run python scripts/verify_data.py

fetch-data:
	uv run python scripts/fetch_data.py

ingest:
ifdef STAGING
	STAGING_DIR=$(STAGING) uv run python scripts/ingest_data.py
else
	uv run python scripts/ingest_data.py
endif

docker-up:
	docker compose up -d --build

docker-logs:
	docker compose logs -f app

docker-down:
	docker compose down
