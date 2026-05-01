PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3.11)

.PHONY: install sample-data test run lint

install:
	python3.11 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev,charts]"

sample-data:
	$(PYTHON) scripts/generate_sample_data.py

test:
	$(PYTHON) -m pytest

run:
	$(PYTHON) -m streamlit run app.py --server.headless true --browser.gatherUsageStats false

lint:
	$(PYTHON) -c "import importlib.util, subprocess, sys; cmd=[sys.executable, '-m', 'ruff', 'check', '.'] if importlib.util.find_spec('ruff') else [sys.executable, '-m', 'compileall', '-q', 'app.py', 'src', 'scripts', 'tests']; raise SystemExit(subprocess.call(cmd))"
