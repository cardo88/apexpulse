# Puerta de entrada a todos los comandos del proyecto.
# Los targets con comentario "##" aparecen en make help y en docs/ai/mapa-codigo.md.

CORE := services/core
UV_RUN := uv run --locked --directory $(CORE)
PYTHON ?= python3
DATA_DIR ?= $(CURDIR)/data

.PHONY: help setup check lint typecheck test check-docs check-skills check-private mapa fetch normalize replay fixture golden-update escanear calibrar

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

fetch: ## Descarga y cachea una sesión de OpenF1 (SESSION=<id>; FORCE=1 ignora la caché)
	@test -n "$(SESSION)" || { echo "Uso: make fetch SESSION=2026-sao-paulo-r" >&2; exit 2; }
	@$(UV_RUN) python -m apexpulse fetch $(SESSION) --data-dir $(DATA_DIR) $(if $(FORCE),--force)

normalize: ## Genera los eventos canónicos v1 en data/canonical (SESSION=<id>; requiere make fetch)
	@test -n "$(SESSION)" || { echo "Uso: make normalize SESSION=2026-sao-paulo-r" >&2; exit 2; }
	@$(UV_RUN) python -m apexpulse normalize $(SESSION) --data-dir $(DATA_DIR)

replay: ## Reproduce una sesión por consola (SESSION=<id> [SPEED=<n>] [NOWAIT=1] [FROM_LAP=<n>] [VERBOSE=1])
	@test -n "$(SESSION)" || { echo "Uso: make replay SESSION=2026-sao-paulo-r SPEED=30" >&2; exit 2; }
	@$(UV_RUN) python -m apexpulse replay $(SESSION) --data-dir $(DATA_DIR) \
		$(if $(NOWAIT),--no-wait,--speed $(or $(SPEED),1)) $(if $(FROM_LAP),--from-lap $(FROM_LAP)) $(if $(VERBOSE),--verbose)

fixture: ## Recorta el crudo a una ventana y regraba fixtures/sessions (SESSION=<id> DESDE=<iso> HASTA=<iso> LAPS=<a>-<b> [SALIDA=<dir>] [VACIAR=<endpoints>])
	@test -n "$(SESSION)" -a -n "$(DESDE)" -a -n "$(HASTA)" -a -n "$(LAPS)" || { echo "Uso: make fixture SESSION=2026-monaco-r DESDE=2026-06-07T14:15 HASTA=2026-06-07T15:15 LAPS=57-70" >&2; exit 2; }
	@$(UV_RUN) python -m apexpulse fixture $(SESSION) --data-dir $(DATA_DIR) --desde $(DESDE) --hasta $(HASTA) --vueltas $(LAPS) \
		--salida $(or $(SALIDA),$(CURDIR)/fixtures/sessions/$(SESSION)/openf1) $(if $(VACIAR),--vaciar $(VACIAR))

golden-update: ## Regraba tests/golden con la salida actual y muestra el diff (SESSION=<id> para una sola sesión)
	@$(UV_RUN) pytest tests/test_golden.py --golden-update -q $(if $(SESSION),-k $(SESSION))
	@git diff --stat -- $(CORE)/tests/golden
	@echo "golden-update: revisar el diff completo (git diff $(CORE)/tests/golden) y poner el motivo en el commit"

escanear: ## Escaneo de solo lectura de las carreras de OpenF1 de un año (YEAR=<año>; EXCLUIR=<slugs,...>)
	@test -n "$(YEAR)" || { echo "Uso: make escanear YEAR=2026" >&2; exit 2; }
	@$(UV_RUN) python -m apexpulse escanear $(YEAR) --data-dir $(DATA_DIR) \
		--fixtures-dir $(CURDIR)/fixtures/sessions $(if $(EXCLUIR),--excluir $(EXCLUIR))

calibrar: ## Intentos reales de undercut y tablas de calibración (SESIONES=<id,id,...>; K=<n,n,...>)
	@$(UV_RUN) python -m apexpulse calibrar --data-dir $(DATA_DIR) \
		$(if $(SESIONES),--sesiones $(SESIONES)) $(if $(K),--k $(K))
