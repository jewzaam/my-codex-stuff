.PHONY: check help reconcile test-unit test-quality

HOME_DIR := $(subst \,/,$(HOME))
CODEX_DIR ?= $(HOME_DIR)/.codex
PYTHON ?= python3

.DEFAULT_GOAL := check

check: test-quality test-unit  ## Run the quality gate


reconcile:  ## Merge repository files into ~/.codex
	install -d "$(CODEX_DIR)"
	$(PYTHON) scripts/reconcile.py
	install -m 700 codex/observe-hook.py "$(CODEX_DIR)/observe-hook.py"
	@echo "Reconciled Codex config to $(CODEX_DIR)"

test-unit:  ## Run unit tests
	$(PYTHON) -m unittest discover -s tests -v

test-quality:  ## Validate Python, TOML, and JSON files
	$(PYTHON) -m py_compile scripts/reconcile.py codex/observe-hook.py tests/test_reconcile.py tests/test_hooks.py
	$(PYTHON) -c 'import json, pathlib, tomllib; root = pathlib.Path("."); json.loads((root / "codex/hooks.json").read_text()); tomllib.loads((root / "codex/config.toml").read_text())'

help:  ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-20s %s\n", $$1, $$2}'
