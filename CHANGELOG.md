# Changelog

Todos los cambios relevantes de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

## [Unreleased]

### Added
- Estructura inicial del repositorio, licencia MIT y aviso de proyecto no oficial.
- Instrucciones para agentes (`AGENTS.md`, `CLAUDE.md`) y skills `cambio-documentado`, `nuevo-adr` y `sesion-replay`.
- Documentación base: índice, roadmap, arquitectura, fuentes de datos y contexto para agentes.
- ADR 0001 a 0008 con las decisiones iniciales.
- Capa privada en `.private/`, ignorada por este repositorio, y verificación `make check-private` que impide versionarla.
- Plantilla de pull request con el bloque "Docs".
- Paquete `apexpulse` mínimo en `services/core/` (uv, Python 3.13) con ruff, mypy estricto y pytest.
- CI en GitHub Actions: ruff, mypy, pytest, `check-docs`, `check-skills` y `check-private` en cada PR y en main.
- `make setup`, `make lint`, `make typecheck`, `make test`, `make check-docs`, `make check-skills`, `make mapa` y `make help`.
- `scripts/check_docs.py`: CHANGELOG, matriz de documentación, enlaces relativos, límites de líneas y mapa al día.
- `scripts/check_skills.py`: formato Agent Skills y correspondencia con la tabla de skills de `AGENTS.md`.
- `docs/ai/mapa-codigo.md`, generado por `make mapa`, y `docs/setup-local.md` con requisitos y verificaciones.
- Hook Stop de Claude Code que corre `make -s check-docs WARN=1` y hook pre-commit que corre `make check-private`.
- Adaptador OpenF1 (`sources/openf1.py`) con caché local en `data/raw`, límite de 3 req/s y 30 req/min compartido entre ejecuciones, reintentos con backoff ante 429, 5xx y errores de red, y validación de esquema por endpoint.
- `make fetch SESSION=<id>` (`python -m apexpulse fetch`), con `FORCE=1` para ignorar la caché.
- Identificador de sesión `<año>-<circuito>-<tipo>` y tabla de circuitos en `services/core/src/apexpulse/config/circuits.toml`.
- Crudo en JSONL zstd con manifiesto por sesión (`sources/rawstore.py`).
- Test de contrato de OpenF1 con respuestas grabadas de `2026-sao-paulo-r` y bloqueo de red en los tests.
- Skill `fuente-de-datos` y `docs/runbook.md` con los errores de descarga.

### Fixed
- `make check-private` ya no falla en un clon sin `.private/` (por ejemplo, en CI).
