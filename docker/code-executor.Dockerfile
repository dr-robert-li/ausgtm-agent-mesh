# Prompt-to-code sandbox image.
#
# POC HARDENING NOTE: this image applies basic least-privilege defaults
# (non-root user, read-only-friendly layout, no extra tooling). It is NOT a
# production isolation boundary on its own. Production MUST run this under a
# stronger sandbox runtime (gVisor / Kata or equivalent) with no host FS/network
# access, scoped short-lived service accounts, and default-deny egress.
# See docs/production-readiness-caveats.md §1.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements/base.txt requirements/base.txt
RUN pip install --no-cache-dir -r requirements/base.txt

COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Run as an unprivileged user with an ephemeral, isolated work directory.
RUN useradd --create-home --uid 10001 sandbox \
    && mkdir -p /workspace && chown sandbox:sandbox /workspace
USER sandbox
WORKDIR /workspace

ENV SANDBOX_MODE=true

CMD ["python", "-m", "agent_mesh.worker.main"]
