# Admin / operator console image: Streamlit. Runs locally and on Cloud Run.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/gui.txt

COPY pyproject.toml ./
COPY src/ src/
COPY manifests/ manifests/
RUN pip install --no-cache-dir -e .

# Cloud Run sets PORT; default to 8501 for local runs.
ENV PORT=8501
EXPOSE 8501

CMD ["sh", "-c", "streamlit run src/agent_mesh/gui/admin_app.py --server.port ${PORT} --server.address 0.0.0.0"]
