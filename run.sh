#!/usr/bin/env bash
# Run the AI Desktop Agent: build the frontend, then launch the backend window.
# Usage: ./run.sh   (Git Bash / WSL / macOS)
set -euo pipefail

cd "$(dirname "$0")"

# --- Optional: redirect uv/npm caches off a full system drive. ---
# If your system drive has no space, uncomment and point these somewhere with room:
# export UV_PYTHON_INSTALL_DIR="$PWD/.uv/python"
# export UV_CACHE_DIR="$PWD/.uv/cache"
# export npm_config_cache="$PWD/.npm-cache"

echo "[1/3] Building frontend..."
( cd frontend && npm install && npm run build )

echo "[2/3] Syncing backend deps..."
( cd backend && uv sync )

echo "[3/3] Launching app..."
( cd backend && uv run python -m agent.main )
