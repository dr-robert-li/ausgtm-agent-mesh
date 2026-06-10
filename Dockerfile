# Shared application image (D-01) for the Phase-10 full-stack local compose.
#
# ONE image, command-parameterized: api, worker, and gui are three compose
# services that differ ONLY by their `command:` (selected in docker-compose.yml,
# plan 10-02). They all run from this same artifact so the local compose proves
# the same image GCP Cloud Run would run (deploy-fidelity — scripts/gcp_deploy_core.sh
# names agent-mesh-api / -worker / -code-executor; the parity surface is the compose
# SERVICE names, not separate Dockerfiles).
#
#   api    -> uvicorn agent_mesh.api.app:app --port 8080
#   worker -> python -m agent_mesh.worker.main
#   gui    -> streamlit run src/agent_mesh/gui/admin_app.py
#
# There is deliberately NO single ENTRYPOINT locking one service; `command:` per
# compose service selects the entrypoint.
#
# Finding #2 (worker DooD): the worker shells out to the docker CLI
# (src/agent_mesh/sandbox/executor.py -> subprocess.run(["docker", ...]) gated by
# shutil.which("docker")). This image therefore carries the docker CLI *client*
# binary (the `docker-cli` OS package — `docker.io` on this trixie-slim base ships
# only the daemon, not the client). The python `docker` SDK is NOT used and is
# intentionally NOT installed. The privileged docker-socket mount + socket-gid
# handling that makes the CLI usable is wired in compose (10-02), NOT baked here.

# Concrete pinned base satisfying pyproject requires-python = ">=3.11".
# No floating :latest tag.
FROM python:3.12-slim

# Stable Python runtime behaviour inside the container.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # pythonpath=src convention: resolve the `agent_mesh` package from /app/src.
    PYTHONPATH=/app/src

# OS packages:
#   - docker-cli -> the docker *client* binary (/usr/bin/docker) for the worker
#                   DooD path (Finding #2). On Debian trixie the client is split
#                   out of `docker.io` (which ships only the daemon dockerd) into
#                   the `docker-cli` package — the worker needs ONLY the client
#                   (it talks to the host daemon over the mounted socket, 10-02).
#                   This is NOT the python docker SDK (intentionally not installed).
#   - ca-certificates -> TLS roots for httpx/litellm calls.
# Installed from the base distro repo (no third-party apt source).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        docker-cli \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the whole build context; .dockerignore prunes .venv/.git/.sbxwork/caches
# and the active config swap state so the build context (and image layer) stay
# lean and free of local/secret state. COPY . (not an enumerated list) guarantees
# src/, config/, migrations/, pyproject.toml, and requirements/ all land under /app.
COPY . /app

# Install the project with the three optional-dependency groups the three
# service commands need, in ONE shared image (D-01):
#   runtime -> litellm, langchain-litellm, langfuse, psycopg, mcp, slack-bolt, otel
#   agents  -> langchain, langgraph (+ checkpointers), deepagents
#   gui     -> streamlit
# The literal `.[runtime,agents,gui]` form (no spaces) is load-bearing.
RUN pip install ".[runtime,agents,gui]"

# No ENTRYPOINT / CMD: compose `command:` selects api | worker | gui per service.
