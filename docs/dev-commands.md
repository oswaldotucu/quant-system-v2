# Development Commands

Package manager is **uv** (not pip). Python **3.12 only** (numba/llvmlite require <3.13).

```bash
# Setup
make install           # uv sync --all-extras + pre-commit install

# Development
make dev               # uvicorn webapp.main:app --reload --port 8080

# Quality
make check             # lint + typecheck + unit tests (run before every commit)
make lint              # ruff check + ruff format --check
make typecheck         # pyright src/
make format            # ruff auto-fix + format

# Testing
make test              # unit + integration tests
make test-regression   # regression tests (needs real data in data/raw/)
make test-slow         # slow tests (Optuna runs)
make test-all          # everything

# Single test
uv run pytest tests/unit/test_metrics.py -v
uv run pytest tests/unit/test_metrics.py::test_profit_factor -v

# Data
make copy-data         # copies CSVs from DATA_SRC into data/raw/
make verify-data       # validates data integrity
make fetch-data        # downloads via yfinance

# Docker
make docker-up         # docker compose up -d --build
make docker-down       # docker compose down
```
