.PHONY: help setup format check clean start stop status index prepare check-mode

PYTHON := .venv/bin/python
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
MODE ?= online
ACCELERATOR ?= auto
CHATBOT_OUTPUT ?= /home/superman/workspaces/chatbot_bca.zip
IMAGES_OUTPUT ?= /home/superman/workspaces/images.zip
MODELS_OUTPUT ?= /home/superman/workspaces/models.zip

help:
	@echo "Chatbot BCA"
	@echo
	@echo "  make setup                 Install locked development dependencies"
	@echo "  make format                Format Python source and tests"
	@echo "  make check                 Run lint, type, compile, and isolated tests"
	@echo "  make start [MODE=online]   Build, start, and index the online stack"
	@echo "  make start MODE=offline    Start the installed offline stack"
	@echo "  make stop [MODE=...]       Stop the selected stack"
	@echo "  make status [MODE=...]     Show the selected stack status"
	@echo "  make index [MODE=...]      Rebuild the selected stack indexes"
	@echo "  make prepare               Create chatbot_bca.zip, images.zip, and models.zip from Git HEAD"
	@echo "  make clean                 Remove generated Python caches"
	@echo
	@echo "Variables: MODE=online|offline ACCELERATOR=auto|cpu|gpu"
	@echo "           CHATBOT_OUTPUT=$(CHATBOT_OUTPUT)"
	@echo "           IMAGES_OUTPUT=$(IMAGES_OUTPUT)"
	@echo "           MODELS_OUTPUT=$(MODELS_OUTPUT)"

setup:
	uv sync --dev --frozen

format:
	$(RUFF) format src tests app.py

check:
	$(RUFF) check src tests app.py
	.venv/bin/mypy src app.py
	$(PYTHON) -m compileall -q src app.py
	$(PYTEST) -q -m "not integration"

check-mode:
	@case "$(MODE)" in online|offline) ;; *) echo "MODE must be online or offline" >&2; exit 2;; esac

start: check-mode
	@if [ "$(MODE)" = online ]; then \
		test -f .env || cp .env.example .env; \
		./scripts/accelerator.sh online "$(ACCELERATOR)" start; \
	else \
		./scripts/offline/offline.sh start; \
	fi

stop: check-mode
	@if [ "$(MODE)" = online ]; then \
		./scripts/accelerator.sh online "$(ACCELERATOR)" stop; \
	else \
		./scripts/offline/offline.sh stop; \
	fi

status: check-mode
	@if [ "$(MODE)" = online ]; then \
		./scripts/accelerator.sh online "$(ACCELERATOR)" status; \
	else \
		./scripts/offline/offline.sh status; \
	fi

index: check-mode
	@if [ "$(MODE)" = online ]; then \
		./scripts/accelerator.sh online "$(ACCELERATOR)" index; \
	else \
		./scripts/offline/offline.sh reindex; \
	fi

prepare:
	./scripts/prepare.sh "$(CHATBOT_OUTPUT)" "$(IMAGES_OUTPUT)" "$(MODELS_OUTPUT)"

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

.DEFAULT_GOAL := help
