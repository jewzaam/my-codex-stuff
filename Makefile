.PHONY: check help install-guards reconcile test-unit test-quality

HOME_DIR := $(subst \,/,$(HOME))
CODEX_DIR ?= $(HOME_DIR)/.codex
PYTHON ?= python3
# The PreToolUse guards are a dependency, not a copy: my-claude-stuff owns the
# one definition and ships it as the `harness_guards` package. A sibling
# checkout by default; a git URL works the same:
#   make install-guards GUARDS_SOURCE=git+https://github.com/jewzaam/my-claude-stuff
GUARDS_SOURCE ?= ../my-claude-stuff
# Externally-managed interpreters (Debian, Fedora system python) reject a bare
# --user install. pip says so and names the flag; pass it here.
#   make install-guards PIP_FLAGS=--break-system-packages
PIP_FLAGS ?=

.DEFAULT_GOAL := check

check: test-quality test-unit  ## Run the quality gate


reconcile: install-guards  ## Merge repository files into ~/.codex
	install -d "$(CODEX_DIR)"
	$(PYTHON) scripts/reconcile.py
	install -m 700 codex/observe-hook.py "$(CODEX_DIR)/observe-hook.py"
	@echo "Reconciled Codex config to $(CODEX_DIR)"

# Part of reconcile on purpose: hooks.json names `harness_guards` modules, and
# `python3 -m` on a missing module exits 1, which Codex reads as a hook error
# and not as a block. Deploying the registration without the package would
# leave the guards silently off.
install-guards:  ## Install the harness_guards dependency for $(PYTHON)
	$(PYTHON) -m pip install --user $(PIP_FLAGS) "$(GUARDS_SOURCE)"

test-unit:  ## Run unit tests
	$(PYTHON) -m unittest discover -s tests -v

test-quality:  ## Validate Python, TOML, and JSON files
	$(PYTHON) -m py_compile scripts/reconcile.py codex/observe-hook.py tests/*.py
	$(PYTHON) -c 'import json, pathlib, tomllib; root = pathlib.Path("."); json.loads((root / "codex/hooks.json").read_text()); tomllib.loads((root / "codex/config.toml").read_text())'

help:  ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-20s %s\n", $$1, $$2}'
