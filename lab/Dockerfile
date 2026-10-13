FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first, so code changes don't invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --system --no-create-home app
USER app
EXPOSE 8000
