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

### Fixed
- `make check-private` ya no falla en un clon sin `.private/` (por ejemplo, en CI).
