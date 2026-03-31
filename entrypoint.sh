#!/usr/bin/env bash
# Wait for Ollama, pull any missing models, then exec the requested command.
set -euo pipefail

python3 /app/pull_models.py

exec "$@"
