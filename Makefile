.PHONY: setup lint format test test-floor eval demo clean

PYTHON ?= .venv/Scripts/python.exe
UV ?= uv

setup:
	$(UV) venv
	$(UV) pip install -r requirements.txt

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m black --check .

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m black .

test:
	$(PYTHON) -m pytest -v tests/

test-floor:
	$(PYTHON) -m pytest -v tests/test_floor.py

eval:
	$(PYTHON) evaluate.py

clean:
	rm -rf .pytest_cache .ruff_cache .hypothesis __pycache__ seller/__pycache__ tests/__pycache__ buyers/__pycache__
