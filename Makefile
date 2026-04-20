COMPOSE_FILE := compose.download.yaml
APP_SERVICE := adrift-download
DOCKER_COMPOSE ?= docker compose
ARGS ?=

.PHONY: help download merge build

help:
	@printf '%s\n' \
		'Available targets:' \
		'  make help                  Show this help text' \
		'  make download ARGS="..."   Run adrift-download in Docker' \
		'  make merge ARGS="..."      Run adrift-merge in Docker' \
		'  make build                 Build the Docker image used by make targets'

build:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) build $(APP_SERVICE)

download:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) run --build --rm $(APP_SERVICE) $(ARGS)

merge:
	$(DOCKER_COMPOSE) -f $(COMPOSE_FILE) run --build --rm --entrypoint adrift-merge $(APP_SERVICE) $(ARGS)