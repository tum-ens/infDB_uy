#!/usr/bin/env bash
# Alternative to Docker: needs uv (https://docs.astral.sh/uv/) and the libarchive system library.
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Install it (https://docs.astral.sh/uv/getting-started/installation/) or use: docker compose up --build" >&2
  exit 1
fi
uv sync --frozen
exec uv run infdb-uy start "$@"
