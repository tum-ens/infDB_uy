# InfDB Uruguay – data pipeline + explorer dashboard
FROM python:3.12-slim

# libarchive: unpacking RAR/7z archives from INE (used through libarchive-c)
RUN apt-get update \
 && (apt-get install -y --no-install-recommends libarchive13t64 || apt-get install -y --no-install-recommends libarchive13) \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app
# dependencies first (cached layer), then the project itself
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable
COPY config ./config

EXPOSE 8050
# Runs the pipeline (finished steps are skipped) and then serves the dashboard.
CMD ["infdb-uy", "start", "--host", "0.0.0.0", "--port", "8050"]
