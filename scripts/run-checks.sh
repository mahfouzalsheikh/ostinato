#!/usr/bin/env bash
set -euo pipefail

python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy src tests

