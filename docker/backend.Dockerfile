FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BENCHMARK_DATA_DIR=/app/volumes \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-default-groups --group backend --no-cache

COPY backend ./backend
COPY cli ./cli
COPY shared ./shared
COPY config ./config
COPY audio ./audio

VOLUME ["/app/volumes"]
EXPOSE 8000

# Keep one API worker: it owns the local task scheduler and SQLite write lifecycle.
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
