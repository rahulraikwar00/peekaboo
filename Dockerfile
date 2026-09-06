FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.10-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build artifacts only; frontend sources are not needed at runtime.
COPY --from=frontend /build/frontend/dist /app/frontend/dist
COPY server /app/server
COPY supabase_schema.sql /app/supabase_schema.sql

EXPOSE 8000

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]