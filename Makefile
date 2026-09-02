# Blessed entry points. Everything a stranger needs to run the project lives here.

.PHONY: help hard-cases install install-serve install-semantic-cache test demo whatif thermostat agent rag agent-live voi-contrast eval eval-real eval-aggregate eval-eta conformal-real experiment calibration serve traffic web-install web-dev web-build lint clean

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
	@echo "make voi-contrast - show the VoI rule SKIP a check on a safe response but BUY one on an uncertain one"
	@echo "make experiment - no-oversight vs fixed-check vs ControlPlane (adaptive), with the model tier on"
	@echo "make eval       - run the evaluation harness on the synthetic seed (P/R/F1/FPR/FNR, baselines)"
	@echo "make eval-real  - eval on a real benchmark (HaluEval), now with 95% CIs; add ARGS='--models' for HHEM"
	@echo "make eval-aggregate - leakage-aware aggregate public-data benchmark; add ARGS='--dataset halueval --limit 500 --warmup 20 --repeats 3'"
	@echo "make hard-cases - screen candidate failure cases against the live model (needs a running Tower)"
	@echo "make eval-eta   - fit detector informativeness η from leakage-safe HaluEval forced-check data"
	@echo "make conformal-real - build real-data escaped-failure conformal certificates"
	@echo "make serve      - run The Tower: proxy + dashboard (:8000); serves the React UI if web/out exists, else lite"
	@echo "make traffic    - fire the scripted demo workload at a running Tower (one-line base_url swap)"
	@echo "make web-build  - build the Next.js UI to a static export so 'make serve' ships it as ONE service"
	@echo "make web-dev    - run the Next.js UI with hot reload (:3000), proxying /api to the backend"
	@echo "make lint       - run ruff over the codebase"
	@echo "make clean      - remove caches and build artifacts"

# Prefer the platform's Python for creating the environment, then use the
# venv interpreter directly so make works without an activation shell.
ifeq ($(OS),Windows_NT)
PYTHON ?= python
VENV_PYTHON := .\.venv\Scripts\python.exe
VENV_ACTIVATE_MSG := .\.venv\Scripts\Activate.ps1
else
PYTHON ?= python3
VENV_PYTHON := .venv/bin/python
VENV_ACTIVATE_MSG := source .venv/bin/activate
endif

install:
	$(PYTHON) -m venv .venv
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e ".[dev]"
	@echo "Done. Activate with: $(VENV_ACTIVATE_MSG)"

install-serve:
	$(VENV_PYTHON) -m pip install -e ".[dev,serve]"
	@echo "Proxy deps installed. Run: make serve"

install-semantic-cache:
	$(VENV_PYTHON) -m pip install -e ".[dev,serve,semantic-cache]"
	@echo "Semantic-cache embeddings installed. Enable with CONTROLPLANE_SEMANTIC_CACHE=1"

test:
	$(VENV_PYTHON) -m pytest

demo:
	$(VENV_PYTHON) -m controlplane.demo.run_demo

whatif:
	$(VENV_PYTHON) -m controlplane.demo.run_whatif

thermostat:
	$(VENV_PYTHON) -m controlplane.demo.run_thermostat

agent:
	$(VENV_PYTHON) -m controlplane.demo.run_agent

rag:
	$(VENV_PYTHON) -m controlplane.demo.run_rag $(ARGS)

agent-live:
	$(VENV_PYTHON) -m controlplane.demo.run_live_agent $(ARGS)

voi-contrast:
	$(VENV_PYTHON) -m controlplane.demo.run_voi_contrast

eval:
	$(VENV_PYTHON) -m controlplane.eval.run

eval-real:
	$(VENV_PYTHON) -m controlplane.eval.run_real --dataset halueval --limit 500 $(ARGS)

eval-aggregate:
	$(VENV_PYTHON) -m controlplane.eval.aggregate --dataset halueval --limit 500 --warmup 20 --repeats 3 $(ARGS)

eval-eta:
	$(VENV_PYTHON) -m controlplane.eval.run_eta $(ARGS)

hard-cases:
	$(VENV_PYTHON) -m controlplane.eval.run_hard_cases $(ARGS)
	@echo "Wrote artifacts/hard_cases.json -- the Hard cases panel reads it"

conformal-real:
	$(VENV_PYTHON) -m controlplane.eval.run_conformal_real --dataset halueval --limit 1000 $(ARGS)

calibration:
	$(VENV_PYTHON) -m controlplane.eval.run_calibration $(ARGS)

serve:
	$(VENV_PYTHON) -m controlplane.proxy

# Recording / full-demo launch: turns on every model-backed detector we ship (HHEM-2.1 groundedness and the
# Groq judge auto-enable from the installed extras + your GROQ_API_KEY; this also flips on Presidio PII, the
# gpt-oss-safeguard content-safety model, and the real semantic cache), and warms them so /readyz waits for
# them. One command for a maximal, all-green demo. Falls back gracefully if any model is unavailable.
serve-demo:
	CONTROLPLANE_USE_PRESIDIO=1 CONTROLPLANE_USE_GROQ_SAFETY=1 CONTROLPLANE_SEMANTIC_CACHE=1 CONTROLPLANE_WARMUP=1 \
		$(VENV_PYTHON) -m controlplane.proxy

traffic:
	$(VENV_PYTHON) -m controlplane.proxy.traffic

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
	$(VENV_PYTHON) -m controlplane.eval.run_experiment --dataset synthetic --models $(ARGS)
	@echo "\n  For the large-n version: make experiment ARGS=\"--dataset halueval --limit 400\""
