# Worker image: long-running AG2 mesh execution for Cloud Run Jobs / Worker Pools.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/worker.txt

COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Long-running consumer; no port. Cloud Run Jobs invokes the entrypoint directly.
CMD ["python", "-m", "agent_mesh.worker.main"]
