#!/usr/bin/env bash
# Installs everything needed to run the pipeline: Python packages and dbt packages.
set -euo pipefail

echo "Starting setup..."

# Run from the project root so relative paths resolve
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null; then
    echo "Error: python3 not found. Install Python 3 first."
    exit 1
fi

# Reuse an active venv/conda env; otherwise create an isolated .venv
if [ -n "${VIRTUAL_ENV:-}" ] || [ -n "${CONDA_PREFIX:-}" ]; then
    echo "Using active environment."
else
    if [ ! -d ".venv" ]; then
        echo "Creating virtual environment in .venv ..."
        python3 -m venv .venv
    fi
    source .venv/bin/activate
fi

echo "Installing Python packages..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# dbt_packages/ is gitignored, so dbt_utils must be installed on every fresh clone
echo "Installing dbt packages..."
(cd dbt && dbt deps --profiles-dir .)

# Can't be installed reliably across operating systems, so just warn
command -v duckdb >/dev/null || echo "Note: DuckDB CLI not found. On macOS: brew install duckdb"
command -v docker >/dev/null || echo "Note: Docker not found. Install Docker Desktop to run the Airflow pipeline."

echo "Setup complete."