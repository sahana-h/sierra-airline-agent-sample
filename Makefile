PYTHON ?= python3
VENV := .venv
PY := $(VENV)/bin/python

.PHONY: install run test eval lint format

# Reinstall only when dependencies change.
$(VENV)/.installed: pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -e ".[dev]"
	touch $@

install: $(VENV)/.installed

run: install
	$(PY) -m airline_agent.cli

test: install
	$(PY) -m pytest tests/unit

# pytest exits with 5 when no tests are collected; that is fine until evals exist.
eval: install
	$(PY) -m pytest tests/evals || [ $$? -eq 5 ]

lint: install
	$(PY) -m ruff check src tests
	$(PY) -m ruff format --check src tests
	$(PY) -m mypy src

format: install
	$(PY) -m ruff check --fix src tests
	$(PY) -m ruff format src tests
