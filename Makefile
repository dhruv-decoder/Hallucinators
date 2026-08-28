# Blessed entry points. Everything a stranger needs to run the project lives here.

.PHONY: help install install-serve install-semantic-cache test demo whatif thermostat agent rag agent-live eval eval-real eval-aggregate eval-eta conformal-real serve traffic web-install web-dev web-build lint clean

help:
	@echo "make install    - create .venv and install the core engine + dev tools"
	@echo "make install-serve - also install the proxy/gateway deps (FastAPI, uvicorn)"
	@echo "make install-semantic-cache - install optional sentence-transformer embeddings for semantic response caching"
	@echo "make test       - run the unit tests"
	@echo "make demo       - run the end-to-end oversight demo on sample requests"
	@echo "make whatif     - run the What-If/Replay comparison across oversight policies"
	@echo "make thermostat - run the adaptive thermostat demo (calm -> risky burst -> calm)"
	@echo "make agent      - run the agentic finale (an agent compounds a hallucination; auditor aborts it)"
	@echo "make rag        - run the tiny RAG app overseen end-to-end (grounded PASS vs hallucination repaired)"
	@echo "make agent-live - run a real ReAct tool-agent overseen live (add ARGS='--live' for real Groq)"
	@echo "make eval       - run the evaluation harness on the synthetic seed (P/R/F1/FPR/FNR, baselines)"
	@echo "make eval-real  - eval on a real benchmark (HaluEval), now with 95% CIs; add ARGS='--models' for HHEM"
	@echo "make eval-aggregate - leakage-aware aggregate public-data benchmark; add ARGS='--dataset halueval --limit 500 --warmup 20 --repeats 3'"
	@echo "make eval-eta   - fit detector informativeness η from leakage-safe HaluEval forced-check data"
	@echo "make conformal-real - build real-data escaped-failure conformal certificates"
	@echo "make serve      - run The Tower: proxy + dashboard (:8000); serves the React UI if web/out exists, else lite"
	@echo "make traffic    - fire the scripted demo workload at a running Tower (one-line base_url swap)"
	@echo "make web-build  - build the Next.js UI to a static export so 'make serve' ships it as ONE service"
	@echo "make web-dev    - run the Next.js UI with hot reload (:3000), proxying /api to the backend"
	@echo "make lint       - run ruff over the codebase"
	@echo "make clean      - remove caches and build artifacts"

install:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip && pip install -e ".[dev]"
	@echo "Done. Activate with: source .venv/bin/activate"

install-serve:
	. .venv/bin/activate && pip install -e ".[dev,serve]"
	@echo "Proxy deps installed. Run: make serve"

install-semantic-cache:
	. .venv/bin/activate && pip install -e ".[dev,serve,semantic-cache]"
	@echo "Semantic-cache embeddings installed. Enable with CONTROLPLANE_SEMANTIC_CACHE=1"

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

rag:
	python -m controlplane.demo.run_rag $(ARGS)

agent-live:
	python -m controlplane.demo.run_live_agent $(ARGS)

eval:
	python -m controlplane.eval.run

eval-real:
	python -m controlplane.eval.run_real --dataset halueval --limit 500 $(ARGS)

eval-aggregate:
	python -m controlplane.eval.aggregate --dataset halueval --limit 500 --warmup 20 --repeats 3 $(ARGS)

eval-eta:
	python -m controlplane.eval.run_eta $(ARGS)

conformal-real:
	python -m controlplane.eval.run_conformal_real --dataset halueval --limit 1000 $(ARGS)

calibration:
	python -m controlplane.eval.run_calibration $(ARGS)

serve:
	python -m controlplane.proxy

traffic:
	python -m controlplane.proxy.traffic

web-install:
	cd web && npm ci

web-dev:
	cd web && npm run dev

web-build:
	cd web && NEXT_OUTPUT=export NEXT_PUBLIC_API_BASE= npm run build
	@echo "Built web/out -- 'make serve' now serves the React product UI at /"

lint:
	ruff check controlplane tests

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache **/__pycache__ *.egg-info build dist

experiment:
	python -m controlplane.eval.run_experiment $(ARGS)
