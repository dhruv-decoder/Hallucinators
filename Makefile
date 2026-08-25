# Blessed entry points. Everything a stranger needs to run the project lives here.

.PHONY: help install test demo serve whatif thermostat eval eval-json lint docker-up docker-down clean

help:
	@echo "make install    - create .venv and install runtime + dev tools"
	@echo "make test       - run the unit tests"
	@echo "make demo       - run the end-to-end oversight demo on sample requests"
	@echo "make serve      - start the OpenAI-compatible ControlPlane proxy"
	@echo "make whatif     - run the What-If/Replay comparison across oversight policies"
	@echo "make thermostat - run the adaptive thermostat demo (calm -> risky burst -> calm)"
	@echo "make eval       - run the evaluation harness (P/R/F1/FPR/FNR, latency, baselines, cost, calibration)"
	@echo "make lint       - run ruff over the codebase"
	@echo "make clean      - remove caches and build artifacts"

install:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip && pip install -e ".[dev,serve]"
	@echo "Done. Activate with: source .venv/bin/activate"

test:
	pytest

serve:
	python -m controlplane.proxy

demo:
	python -m controlplane.demo.run_demo

whatif:
	python -m controlplane.demo.run_whatif

thermostat:
	python -m controlplane.demo.run_thermostat

eval:
	python -m controlplane.eval.run

lint:
	ruff check controlplane tests

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache **/__pycache__ *.egg-info build dist


eval-json:
	python -m controlplane.eval.run --json artifacts/eval_report.json

docker-up:
	docker compose up --build

docker-down:
	docker compose down
