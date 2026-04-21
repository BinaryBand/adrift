COMPOSE_FILE := compose.download.yaml
APP_SERVICE := adrift-download
DOCKER_COMPOSE ?= docker compose
ARGS ?=

# Use virtualenv python if present
PYTHON ?= $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)
PYRIGHT ?= $(shell [ -x .venv/bin/pyright ] && echo .venv/bin/pyright || echo pyright)

.PHONY: quality ruff-format ruff-format-check ruff-check ruff-check-src ruff-check-tests validate-configs check-complexity check-dead-code check-import-boundaries
.PHONY: quality ruff-format ruff-format-check ruff-format-src ruff-format-tests ruff-check ruff-check-src ruff-check-tests ruff vulture pyright lizard validate-configs check-complexity check-dead-code check-import-boundaries

.PHONY: help download merge build

help:
	@printf '%s\n' \
		'Available targets:' \
		'  make help                  Show this help text' \
		'  make download ARGS="..."   Run adrift-download in Docker' \
		'  make merge ARGS="..."      Run adrift-merge in Docker' \
		'  make build                 Build the Docker image used by make targets' \
		'  make ruff-format           Run ruff formatter across the repo' \
		'  make ruff-format-check     Check ruff formatting (no changes)' \
		'  make ruff-format-src       Run ruff formatter on source only' \
		'  make ruff-format-tests     Run ruff formatter on tests only' \
		'  make ruff-check            Run ruff linter checks' \
		'  make ruff-check-src        Run ruff checks for source only' \
		'  make ruff-check-tests      Run ruff checks for tests only' \
		'  make ruff                  Alias for make ruff-check' \
		'  make vulture               Run vulture dead-code checks' \
		'  make pyright               Run pyright type checks' \
		'  make lizard                Run lizard complexity gates' \
		'  make validate-configs      Validate TOML podcast configs' \
		'  make check-complexity      Run lizard complexity checks' \
		'  make check-dead-code       Run vulture dead-code checks' \
		'  make check-import-boundaries  Enforce simple import-boundary rules'

build:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) build $(APP_SERVICE)

download:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) run --build --rm $(APP_SERVICE) $(ARGS)

merge:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) run --build --rm --entrypoint adrift-merge $(APP_SERVICE) $(ARGS)

# ---------------------------------------------------------------------------
# Quality targets (wrap runbook/quality modules)
# ---------------------------------------------------------------------------


# Ruff formatting and checks
ruff:
	$(MAKE) ruff-check

format:
	$(PYTHON) -m ruff format src runbook tests typings

vulture:
	$(MAKE) check-dead-code

pyright:
	$(PYRIGHT) --project pyrightconfig.json

lizard:
	$(MAKE) check-complexity

validate-configs:
	$(PYTHON) -m runbook.quality.validate_configs --problems

check-complexity:
	$(PYTHON) -m runbook.quality.check_complexity --ccn 8 --length 30 --params 4

check-dead-code:
	$(PYTHON) -m runbook.quality.check_dead_code --strict

check-import-boundaries:
	$(PYTHON) -m runbook.quality.check_import_boundaries --strict