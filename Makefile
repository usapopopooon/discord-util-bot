.PHONY: setup install dev test lint typecheck run clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

setup: $(VENV)/bin/activate

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

install: setup

dev: setup
	$(PIP) install -e ".[dev]"

test: setup
	$(PYTHON) -m pytest

lint: setup
	$(VENV)/bin/ruff check src tests

typecheck: setup
	$(VENV)/bin/mypy src

run: setup
	$(PYTHON) -m src.main

clean:
	rm -rf $(VENV)
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf *.egg-info
	rm -rf .coverage
	rm -rf htmlcov
	find . -type d -name "__pycache__" -exec rm -rf {} +
