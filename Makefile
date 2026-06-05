.PHONY: help install install-dev schemas test lint fmt smoke run-api run-worker run-gui

PY ?= python
PYTHONPATH := src

help:
	@echo "Targets:"
	@echo "  install      Install base (contract/service) dependencies"
	@echo "  install-dev  Install all dev dependencies (api + worker + test/lint)"
	@echo "  schemas      Export JSON Schema for all contract models"
	@echo "  test         Run the test suite"
	@echo "  lint         Run ruff lint checks"
	@echo "  fmt          Auto-fix lint + format with ruff"
	@echo "  smoke        Run the local end-to-end smoke check (no DB, no network)"
	@echo "  run-api      Run the FastAPI ingress locally"
	@echo "  run-worker   Drain the in-process task queue once"
	@echo "  run-gui      Run the Streamlit admin/operator console locally"

install:
	$(PY) -m pip install -r requirements/base.txt
	$(PY) -m pip install -e .

install-dev:
	$(PY) -m pip install -r requirements/dev.txt
	$(PY) -m pip install -e ".[dev]"

schemas:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m agent_mesh.contracts.export_schemas

test:
	PYTHONPATH=$(PYTHONPATH) $(PY) -m pytest -q

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
