FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BENCHMARK_DATA_DIR=/app/volumes

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY cli ./cli
COPY shared ./shared
COPY config ./config
COPY audio ./audio

VOLUME ["/app/volumes"]
EXPOSE 8000

# Keep one API worker: it owns the local task scheduler and SQLite write lifecycle.
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
