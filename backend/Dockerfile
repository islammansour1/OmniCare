# OmniCare AI backend — FastAPI service
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install Python dependencies first so this layer is cached across source edits.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the application. `data/mock_claims.json` ships as the only seed data;
# runtime artifacts (SQLite/Chroma/lock files) are excluded via .dockerignore.
COPY . /app

# Writable runtime data dir (SQLite, Chroma, claims). docker-compose mounts a
# named volume here, seeded from this directory on first run. chmod 0777 keeps
# it writable regardless of the runtime user / volume ownership.
RUN mkdir -p /app/data && chmod 0777 /app/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
