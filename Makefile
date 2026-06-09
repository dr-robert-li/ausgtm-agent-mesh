.PHONY: help install install-dev schemas test test-live test-pg lint fmt smoke run-api run-worker run-gui run-vllm run-ollama use-vllm use-ollama use-cloud run-pg

PY ?= python
PYTHONPATH := src

help:
	@echo "Targets:"
	@echo "  install      Install base (contract/service) dependencies"
	@echo "  install-dev  Install all dev dependencies (api + worker + test/lint)"
	@echo "  schemas      Export JSON Schema for all contract models"
	@echo "  test         Run the deterministic test suite (no cloud deps; excludes 'live')"
	@echo "  test-live    Run the opt-in live suite (pytest -m live; needs real creds)"
	@echo "  test-pg      Run the DSN-gated Postgres durable lane (export TEST_DATABASE_URL; loud-skips when unset)"
	@echo "  lint         Run ruff lint checks"
	@echo "  fmt          Auto-fix lint + format with ruff"
	@echo "  smoke        Run the local end-to-end smoke check (no DB, no network)"
	@echo "  run-api      Run the FastAPI ingress locally"
	@echo "  run-worker   Drain the in-process task queue once"
	@echo "  run-gui      Run the Streamlit admin/operator console locally"
	@echo "  run-vllm     Start a local vLLM OpenAI server (GPU; best-effort, never CI)"
	@echo "  run-ollama   Pull + serve the local Ollama model (CPU/dev; best-effort, never CI)"
	@echo "  use-vllm     Swap the local vLLM profile onto config/model_gateway.config.yaml"
	@echo "  use-ollama   Swap the local Ollama profile onto config/model_gateway.config.yaml"
	@echo "  use-cloud    Restore the pristine cloud profile onto config/model_gateway.config.yaml"
	@echo "  run-pg       Start a local pgvector Postgres (best-effort, operator-only, never CI)"

install:
	$(PY) -m pip install -r requirements/base.txt
	$(PY) -m pip install -e .

install-dev:
	$(PY) -m pip install -r requirements/dev.txt
	$(PY) -m pip install -e ".[dev]"

schemas:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m agent_mesh.contracts.export_schemas

test:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -q -m "not live"

test-live:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -q -m live

# Deploy-readiness: run the DSN-gated durable/Postgres checkpointer lane against a real
# pgvector Postgres. Export TEST_DATABASE_URL first (see RUNBOOK.md); the pg_dsn fixture
# loud-skips every Postgres test when it is unset, so this never hard-fails on a machine
# with no Postgres. Not creds-gated -> excludes 'live'.
test-pg:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -q -m "not live" \
		tests/e2e/test_e2e_mcp_durable_job_live.py tests/test_checkpointer_resume.py \
		tests/test_local_data_plane.py

lint:
	$(PY) -m ruff check src tests

fmt:
	$(PY) -m ruff check --fix src tests
	$(PY) -m ruff format src tests

smoke:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m tests.smoke

run-api:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m uvicorn agent_mesh.api.app:app --reload --port 8080

run-worker:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m agent_mesh.worker.main

run-gui:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m streamlit run src/agent_mesh/gui/admin_app.py

# --- Local inference lane (LOCAL-01/02/03) -----------------------------------
# run-vllm / run-ollama actually start a local backend. They are best-effort,
# operator-run, and DELIBERATELY never wired into `test` or any CI path (D-07):
# they require a GPU (vLLM) / an installed Ollama and may fail on a box without
# them, which is acceptable and documented in RUNBOOK.md.
#
# The hermes tool-call parser is baked in for the default Qwen2.5 model (D-08).
# Do NOT carry hermes to a Llama-3.1 model — use llama3_json for that family.
VLLM_MODEL ?= Qwen/Qwen2.5-7B-Instruct
run-vllm:
	vllm serve $(VLLM_MODEL) --port 8000 --enable-auto-tool-choice --tool-call-parser hermes

OLLAMA_MODEL ?= qwen2.5:7b-instruct
run-ollama:
	ollama pull $(OLLAMA_MODEL) && ollama serve

# Profile selection is a reversible file swap (D-01/D-02): copy the chosen
# profile onto the active config/model_gateway.config.yaml. cp (not git checkout,
# Pitfall 5) so it works on a dirty tree / non-git export. use-cloud restores the
# pristine cloud anchor authored in Plan 01.
use-vllm:
	cp config/model_gateway.vllm.yaml config/model_gateway.config.yaml
use-ollama:
	cp config/model_gateway.ollama.yaml config/model_gateway.config.yaml
use-cloud:
	cp config/model_gateway.cloud.yaml config/model_gateway.config.yaml

# --- Local data plane (LDATA-01) ---------------------------------------------
# run-pg starts a single local pgvector Postgres. Best-effort, operator-run, and
# DELIBERATELY never wired into `test` or any CI path: it requires Docker and may
# fail on a box without it, which is acceptable and documented in RUNBOOK.md.
# Creds/port/db MUST match the pinned DATABASE_URL default in .env.example
# (D-01 <-> D-04). Persistent -d + named volume so data survives restarts and
# `make test-pg` can re-run against the same container.
#
# Image is pinned to pgvector/pgvector:pg16: a vanilla postgres image fails the
# CREATE EXTENSION vector migration (0001) — IF NOT EXISTS does not install it.
PG_IMAGE     ?= pgvector/pgvector:pg16
PG_CONTAINER ?= agent_mesh_pg
PG_VOLUME    ?= agent_mesh_pgdata
run-pg:
	docker run -d --name $(PG_CONTAINER) \
	  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=agent_mesh \
	  -p 5432:5432 -v $(PG_VOLUME):/var/lib/postgresql/data \
	  $(PG_IMAGE)
