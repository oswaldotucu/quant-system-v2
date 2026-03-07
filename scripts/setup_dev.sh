#!/usr/bin/env bash
# First-time dev environment setup.
# Run once after cloning: bash scripts/setup_dev.sh

set -e

echo "=== quant-v2 dev setup ==="

# 1. Check Python version
python3 --version
PYVER=$(python3 -c "import sys; print(sys.version_info[:2] >= (3, 12))")
if [ "$PYVER" != "True" ]; then
    echo "ERROR: Python 3.12+ required"
    exit 1
fi

# 2. Install uv if not present
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

# 3. Install Python dependencies
echo "Installing dependencies..."
uv sync --all-extras

# 4. Install pre-commit hooks
echo "Installing pre-commit hooks..."
uv run pre-commit install

# 5. Copy .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example -- review before running"
fi

# 6. Create data directories
mkdir -p data/raw data/db data/pine_scripts data/checklists

echo ""
echo "Setup complete. Next steps:"
echo "  make copy-data     # copy CSVs from old project"
echo "  make verify-data   # confirm data integrity"
echo "  make test-regression"
echo "  make dev           # http://localhost:8080"
