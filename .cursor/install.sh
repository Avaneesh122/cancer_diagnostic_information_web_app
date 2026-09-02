#!/usr/bin/env bash
set -euo pipefail

# Idempotent bootstrap for the Cancer Diagnostic Web App dev environment.

# Install uv (Python package/dependency manager) if it is not already present.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# Create the virtualenv and install pinned dependencies (uv also fetches the
# Python version declared in .python-version). Safe to run repeatedly.
uv sync
