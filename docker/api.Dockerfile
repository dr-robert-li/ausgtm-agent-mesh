# Ingress image: FastAPI app for Slack / MCP / API / approval callbacks.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/api.txt

COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Cloud Run sets PORT; default to 8080 for local runs.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn agent_mesh.api.app:app --host 0.0.0.0 --port ${PORT}"]
