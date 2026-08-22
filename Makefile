# Blessed entry points. Everything a stranger needs to run the project lives here.

.PHONY: help install test demo lint clean

help:
	@echo "make install   - create .venv and install the core engine + dev tools"
	@echo "make test      - run the unit tests"
	@echo "make demo      - run the end-to-end oversight demo on sample requests"
	@echo "make lint      - run ruff over the codebase"
	@echo "make clean     - remove caches and build artifacts"

install:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip && pip install -e ".[dev]"
	@echo "Done. Activate with: source .venv/bin/activate"

test:
	pytest

demo:
	python -m controlplane.demo.run_demo

lint:
	ruff check controlplane tests

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache **/__pycache__ *.egg-info build dist
