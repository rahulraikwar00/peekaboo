# syntax=docker/dockerfile:1

# Stage 1: build the owner dashboard SPA (React/Vite).
FROM node:22-alpine.20 AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: FastAPI backend + prebuilt frontend artifacts.
FROM python:3.10-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1                                     

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build artifacts only; frontend sources are not needed at runtime.
COPY --from=frontend /build/frontend/dist /app/frontend/dist
COPY server /app/server
COPY supabase_schema.sql /app/supabase_schema.sql

# /data holds the SQLite database when STORAGE_BACKEND=sqlite (docker-compose).
RUN mkdir -p /data && chown -R app:app /app /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4)" || exit 1

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]