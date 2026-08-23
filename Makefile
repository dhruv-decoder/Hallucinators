# Blessed entry points. Everything a stranger needs to run the project lives here.

.PHONY: help install install-serve test demo whatif thermostat eval serve traffic lint clean

help:
	@echo "make install    - create .venv and install the core engine + dev tools"
	@echo "make install-serve - also install the proxy/gateway deps (FastAPI, uvicorn)"
	@echo "make test       - run the unit tests"
	@echo "make demo       - run the end-to-end oversight demo on sample requests"
	@echo "make whatif     - run the What-If/Replay comparison across oversight policies"
	@echo "make thermostat - run the adaptive thermostat demo (calm -> risky burst -> calm)"
	@echo "make agent      - run the agentic finale (an agent compounds a hallucination; auditor aborts it)"
	@echo "make eval       - run the evaluation harness (P/R/F1/FPR/FNR, baselines, cost, calibration)"
	@echo "make serve      - run The Tower: OpenAI-compatible proxy + Control-Tower dashboard (:8000)"
	@echo "make traffic    - fire the scripted demo workload at a running Tower (one-line base_url swap)"
	@echo "make lint       - run ruff over the codebase"
	@echo "make clean      - remove caches and build artifacts"

install:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip && pip install -e ".[dev]"
	@echo "Done. Activate with: source .venv/bin/activate"

install-serve:
	. .venv/bin/activate && pip install -e ".[dev,serve]"
	@echo "Proxy deps installed. Run: make serve"

test:
	pytest

demo:
	python -m controlplane.demo.run_demo

whatif:
	python -m controlplane.demo.run_whatif

thermostat:
	python -m controlplane.demo.run_thermostat

agent:
	python -m controlplane.demo.run_agent

eval:
	python -m controlplane.eval.run

serve:
	python -m controlplane.proxy

traffic:
	python -m controlplane.proxy.traffic

lint:
	ruff check controlplane tests

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache **/__pycache__ *.egg-info build dist
