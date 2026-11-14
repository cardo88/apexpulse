# Puerta de entrada a todos los comandos del proyecto.
# Los targets con comentario "##" aparecen en make help y en docs/ai/mapa-codigo.md.

CORE := services/core
UV_RUN := uv run --locked --directory $(CORE)
PYTHON ?= python3

.PHONY: help setup check lint typecheck test check-docs check-skills check-private mapa

help: ## Lista los targets disponibles
	@grep -E '^[a-zA-Z0-9_-]+:.*## ' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | expand -t 16

setup: ## Instala dependencias de Python con uv y activa los hooks de git
	uv sync --locked --directory $(CORE)
	git config core.hooksPath .githooks
	@echo "setup: OK"

check: lint typecheck test check-docs check-skills check-private ## Todas las verificaciones

lint: ## ruff: reglas de estilo y formato
	$(UV_RUN) ruff check . ../../scripts
	$(UV_RUN) ruff format --check . ../../scripts

typecheck: ## mypy en modo estricto
	$(UV_RUN) mypy

test: ## pytest
	$(UV_RUN) pytest

check-docs: ## Docs, CHANGELOG y mapa al día con el cambio (WARN=1 solo avisa)
	@WARN=$(WARN) $(PYTHON) scripts/check_docs.py

check-skills: ## Formato de los skills y tabla de skills de AGENTS.md
	@$(PYTHON) scripts/check_skills.py

check-private: ## Falla si algo de la capa privada quedó versionado
	@scripts/check_private.sh

mapa: ## Regenera docs/ai/mapa-codigo.md
	@$(PYTHON) scripts/mapa.py
