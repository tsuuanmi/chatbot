SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

.DEFAULT_GOAL := help

VERSIONS_ENV ?= versions.env
RUNTIME_ENV ?= .env
APP_TAG ?= chatbot-app:local
ACCELERATOR ?= auto

RUNTIME_STATE_DIR ?= $(shell \
	if [ -f "$(RUNTIME_ENV)" ]; then \
		sed -n \
			's/^CHATBOT_RUNTIME_DIR=//p' \
			"$(RUNTIME_ENV)" \
		| tail -n 1; \
	fi)

AUTH_REGISTRY ?= \
	$(RUNTIME_STATE_DIR)/secrets/chat_auth.json

CLIENT_API_KEY ?= \
	$(RUNTIME_STATE_DIR)/secrets/chat_api_key

GATEWAY_PORT ?= 18080

GATEWAY_URL ?= \
	http://127.0.0.1:$(GATEWAY_PORT)


COMPOSE = env \
	-u CHATBOT_IMAGE \
	-u HAYHOOKS_IMAGE \
	-u LLAMA_CPU_IMAGE \
	-u LLAMA_GPU_IMAGE \
	-u POSTGRES_IMAGE \
	-u NGINX_IMAGE \
	-u EMBEDDING_MODEL \
	-u EMBEDDING_DIMENSION \
	docker compose \
	--env-file $(RUNTIME_ENV) \
	--env-file $(VERSIONS_ENV) \
	-f compose.yaml

GPU_COMPOSE = \
	$(COMPOSE) \
	-f compose.gpu.yaml

TOOLS = \
	$(COMPOSE) \
	--profile tools


.PHONY: \
	help \
	bootstrap \
	up \
	down \
	status \
	logs \
	index \
	test \
	verify \
	release \
	_env \
	_check-host \
	_check-env \
	_pull-images \
	_build \
	_models \
	_secrets \
	_config \
	_migrate \
	_index-knowledge \
	_index-figures


help:
	@printf '%s\n' \
		'chatbot commands' \
		'' \
		'  make bootstrap         Prepare a fresh checkout' \
		'  make up                Start chatbot (auto CPU/GPU)' \
		'  make down              Stop chatbot' \
		'  make status            Show runtime status' \
		'  make logs [SERVICE=x]  Show logs' \
		'  make index             Rebuild knowledge and figure indexes' \
		'  make test              Run unit tests' \
		'  make verify            Run full runtime acceptance' \
		'  make release           Build the runtime release' \
		'' \
		'Options:' \
		'  ACCELERATOR=auto|cpu|gpu   Default: auto'


# ---------------------------------------------------------------------
# Public commands
# ---------------------------------------------------------------------

bootstrap:
	@$(MAKE) _env
	@$(MAKE) _check-host
	@$(MAKE) _pull-images
	@$(MAKE) _build
	@$(MAKE) _models
	@$(MAKE) _secrets
	@$(MAKE) _config
	@echo
	@echo "BOOTSTRAP PASS"
	@echo "Next: make up"


up:
	@$(MAKE) _check-env
	@$(MAKE) _check-host
	@$(MAKE) _secrets
	@$(MAKE) _config
	@set -a; \
	source "$(VERSIONS_ENV)"; \
	source "$(RUNTIME_ENV)"; \
	set +a; \
	requested="$(ACCELERATOR)"; \
	selected="$$requested"; \
	case "$$requested" in \
		auto|cpu|gpu) ;; \
		*) \
			echo \
				"Invalid ACCELERATOR=$$requested; expected auto, cpu, or gpu" \
				>&2; \
			exit 1; \
			;; \
	esac; \
	gpu_memory=""; \
	if [ "$$selected" = "auto" ]; then \
		selected="cpu"; \
		if command -v nvidia-smi >/dev/null 2>&1; then \
			gpu_memory="$$( \
				nvidia-smi \
					--query-gpu=memory.total \
					--format=csv,noheader,nounits \
					2>/dev/null \
				| head -n 1 \
				| tr -d '[:space:]' \
				|| true \
			)"; \
			if \
				[[ "$$gpu_memory" =~ ^[0-9]+$$ ]] \
				&& [ "$$gpu_memory" -ge 6144 ] \
				&& docker run \
					--rm \
					--gpus all \
					"$$LLAMA_GPU_IMAGE" \
					--list-devices \
					2>/dev/null \
					| grep -q 'CUDA0:'; \
			then \
				selected="gpu"; \
			fi; \
		fi; \
	fi; \
	if [ "$$selected" = "gpu" ]; then \
		command -v nvidia-smi >/dev/null 2>&1 || { \
			echo "GPU mode requires nvidia-smi" >&2; \
			exit 1; \
		}; \
		gpu_memory="$$( \
			nvidia-smi \
				--query-gpu=memory.total \
				--format=csv,noheader,nounits \
				2>/dev/null \
			| head -n 1 \
			| tr -d '[:space:]' \
		)"; \
		[[ "$$gpu_memory" =~ ^[0-9]+$$ ]] || { \
			echo "Unable to determine GPU memory" >&2; \
			exit 1; \
		}; \
		[ "$$gpu_memory" -ge 6144 ] || { \
			echo \
				"GPU mode requires at least 6144 MiB VRAM" \
				>&2; \
			exit 1; \
		}; \
		docker run \
			--rm \
			--gpus all \
			"$$LLAMA_GPU_IMAGE" \
			--list-devices \
			2>/dev/null \
			| grep -q 'CUDA0:' \
			|| { \
				echo \
					"Docker NVIDIA runtime is unavailable" \
					>&2; \
				exit 1; \
			}; \
		if [ "$$gpu_memory" -ge 16384 ]; then \
			main_layers=99; \
			draft_layers=99; \
			profile=full; \
		else \
			main_layers=16; \
			draft_layers=0; \
			profile=conservative; \
		fi; \
	fi; \
	needs_init=0; \
	if \
		[ ! -f "$(RUNTIME_STATE_DIR)/.initialized" ] \
		|| ! docker volume inspect \
			chatbot_postgres_data \
			>/dev/null 2>&1; \
	then \
		needs_init=1; \
	fi; \
	echo "Starting PostgreSQL..."; \
	$(COMPOSE) up \
		-d \
		postgres \
		--pull never \
		--wait; \
	$(MAKE) _migrate; \
	if [ "$$needs_init" = "1" ]; then \
		echo "Building initial knowledge index..."; \
		$(MAKE) _index-knowledge; \
	fi; \
	if [ "$$selected" = "gpu" ]; then \
		echo \
			"Starting NVIDIA llama.cpp profile=$$profile memory=$${gpu_memory}MiB layers=$${main_layers}/$${draft_layers}..."; \
		LLAMA_GPU_LAYERS="$$main_layers" \
		LLAMA_GPU_LAYERS_DRAFT="$$draft_layers" \
		$(GPU_COMPOSE) up \
			-d \
			llama-server \
			--pull never \
			--wait; \
	else \
		echo "Starting CPU llama.cpp..."; \
		$(COMPOSE) up \
			-d \
			llama-server \
			--pull never \
			--wait; \
	fi; \
	if [ "$$needs_init" = "1" ]; then \
		echo "Building initial figure index..."; \
		$(MAKE) _index-figures; \
	fi; \
	if [ "$$selected" = "gpu" ]; then \
		LLAMA_GPU_LAYERS="$$main_layers" \
		LLAMA_GPU_LAYERS_DRAFT="$$draft_layers" \
		$(GPU_COMPOSE) up \
			-d \
			chatbot \
			proxy \
			--pull never \
			--wait; \
	else \
		$(COMPOSE) up \
			-d \
			chatbot \
			proxy \
			--pull never \
			--wait; \
	fi; \
	mkdir -p "$(RUNTIME_STATE_DIR)"; \
	touch "$(RUNTIME_STATE_DIR)/.initialized"; \
	echo; \
	echo "UP PASS accelerator=$$selected"; \
	echo "local=$(GATEWAY_URL)"


down: _check-env
	@$(COMPOSE) down


status: _check-env
	@$(COMPOSE) ps
	@cid="$$( \
		$(COMPOSE) ps -q llama-server \
	)"; \
	if [ -n "$$cid" ]; then \
		requests="$$( \
			docker inspect \
				"$$cid" \
				--format \
				'{{json .HostConfig.DeviceRequests}}' \
		)"; \
		if \
			[ "$$requests" != "null" ] \
			&& [ "$$requests" != "[]" ]; \
		then \
			echo "accelerator=gpu"; \
		else \
			echo "accelerator=cpu"; \
		fi; \
	fi


logs: _check-env
	@$(COMPOSE) logs \
		--tail=$${LINES:-200} \
		$(if $(SERVICE),$(SERVICE),)


index:
	@$(MAKE) up \
		ACCELERATOR="$(ACCELERATOR)"
	@echo "Stopping client-facing services..."
	@$(COMPOSE) stop \
		proxy \
		chatbot
	@$(MAKE) _index-knowledge
	@$(MAKE) _index-figures
	@$(COMPOSE) up \
		-d \
		--no-deps \
		chatbot \
		proxy \
		--pull never \
		--wait
	@mkdir -p "$(RUNTIME_STATE_DIR)"
	@touch \
		"$(RUNTIME_STATE_DIR)/.initialized"
	@echo "INDEX PASS"


test:
	@python3 -m unittest \
		discover \
		-s tests/unit \
		-t . \
		-p 'test_*.py' \
		-v


verify: _check-env
	@flag=""; \
	requests="$$( \
		docker inspect \
			chatbot-llama \
			--format \
			'{{json .HostConfig.DeviceRequests}}' \
			2>/dev/null \
			|| true \
	)"; \
	if \
		[ -n "$$requests" ] \
		&& [ "$$requests" != "null" ] \
		&& [ "$$requests" != "[]" ]; \
	then \
		flag="--gpu"; \
	fi; \
	CHAT_AUTH_REGISTRY_PATH="$(AUTH_REGISTRY)" \
	CHAT_CLIENT_API_KEY_FILE="$(CLIENT_API_KEY)" \
	CHAT_GATEWAY_BASE_URL="$(GATEWAY_URL)" \
	python3 -m tools.accept \
		full \
		$$flag


release: _check-env
	@python3 -m tools.release \
		build \
		runtime \
		$(if $(VERSION),--version "$(VERSION)",)


# ---------------------------------------------------------------------
# Internal steps
# ---------------------------------------------------------------------

_env:
	@if [ ! -f "$(RUNTIME_ENV)" ]; then \
		test -f .env.example || { \
			echo "Missing .env.example" >&2; \
			exit 1; \
		}; \
		cp \
			.env.example \
			"$(RUNTIME_ENV)"; \
		sed -i \
			"s/^CHATBOT_SECRET_GID=.*/CHATBOT_SECRET_GID=$$(id -g)/" \
			"$(RUNTIME_ENV)"; \
		chmod \
			600 \
			"$(RUNTIME_ENV)"; \
		echo \
			"Created $(RUNTIME_ENV) from .env.example"; \
	else \
		echo \
			"$(RUNTIME_ENV) already exists; keeping existing configuration"; \
	fi


_check-host:
	@command -v docker >/dev/null 2>&1 || { \
		echo "docker is required" >&2; \
		exit 1; \
	}
	@command -v python3 >/dev/null 2>&1 || { \
		echo "python3 is required" >&2; \
		exit 1; \
	}
	@docker info >/dev/null 2>&1 || { \
		echo "Docker daemon is unavailable" >&2; \
		exit 1; \
	}
	@docker compose version >/dev/null 2>&1 || { \
		echo "Docker Compose plugin is required" >&2; \
		exit 1; \
	}


_check-env:
	@test -f "$(VERSIONS_ENV)" || { \
		echo "Missing $(VERSIONS_ENV)" >&2; \
		exit 1; \
	}
	@test -f "$(RUNTIME_ENV)" || { \
		echo \
			"Missing $(RUNTIME_ENV); run 'make bootstrap' first" \
			>&2; \
		exit 1; \
	}


_pull-images: _check-env
	@set -a; \
	source "$(VERSIONS_ENV)"; \
	set +a; \
	: "$${HAYHOOKS_IMAGE:?HAYHOOKS_IMAGE is required}"; \
	: "$${LLAMA_CPU_IMAGE:?LLAMA_CPU_IMAGE is required}"; \
	: "$${LLAMA_GPU_IMAGE:?LLAMA_GPU_IMAGE is required}"; \
	: "$${POSTGRES_IMAGE:?POSTGRES_IMAGE is required}"; \
	: "$${NGINX_IMAGE:?NGINX_IMAGE is required}"; \
	echo "Pulling pinned Docker images..."; \
	docker pull "$$HAYHOOKS_IMAGE"; \
	docker pull "$$LLAMA_CPU_IMAGE"; \
	docker pull "$$LLAMA_GPU_IMAGE"; \
	docker pull "$$POSTGRES_IMAGE"; \
	docker pull "$$NGINX_IMAGE"


_build: _check-env
	@set -a; \
	source "$(VERSIONS_ENV)"; \
	set +a; \
	: "$${HAYHOOKS_IMAGE:?HAYHOOKS_IMAGE is required}"; \
	: "$${EMBEDDING_MODEL:?EMBEDDING_MODEL is required}"; \
	: "$${EMBEDDING_DIMENSION:?EMBEDDING_DIMENSION is required}"; \
	docker build \
		--build-arg \
			HAYHOOKS_IMAGE="$$HAYHOOKS_IMAGE" \
		--build-arg \
			EMBEDDING_MODEL="$$EMBEDDING_MODEL" \
		--build-arg \
			EMBEDDING_DIMENSION="$$EMBEDDING_DIMENSION" \
		-t "$(APP_TAG)" \
		.; \
	echo "CHATBOT_IMAGE=$(APP_TAG)"


_models: _check-env
	@python3 -m tools.download_models


_secrets: _check-env
	@python3 -m tools.init_secrets
	@CHAT_AUTH_REGISTRY_PATH="$(AUTH_REGISTRY)" \
	CHAT_CLIENT_API_KEY_FILE="$(CLIENT_API_KEY)" \
	python3 -m tools.auth check


_config: _check-env
	@$(COMPOSE) config --quiet
	@echo "COMPOSE CONFIG PASS"


_migrate:
	@$(TOOLS) run \
		--rm \
		db-migrate


_index-knowledge:
	@$(TOOLS) run \
		--rm \
		index-knowledge
	@echo "KNOWLEDGE INDEX PASS"


_index-figures:
	@$(TOOLS) run \
		--rm \
		--no-deps \
		index-figures
	@echo "FIGURE INDEX PASS"
