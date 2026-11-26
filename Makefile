.PHONY: setup lint format test test-floor eval demo batch docker-build docker-test clean

PYTHON ?= .venv/Scripts/python.exe
UV ?= uv
DOCKER ?= docker

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

demo:
	$(PYTHON) -m streamlit run demo/app.py

batch:
	$(PYTHON) experiments/run_batch.py --runs-per-buyer 300 --output outputs/results.jsonl --summary outputs/summary_metrics.csv

docker-build:
	$(DOCKER) build -t vaultline:latest .

docker-test:
	$(DOCKER) run --rm --network none vaultline:latest

clean:
	rm -rf .pytest_cache .ruff_cache .hypothesis __pycache__ seller/__pycache__ tests/__pycache__ buyers/__pycache__
