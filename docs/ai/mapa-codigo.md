# Mapa de código

Generado por `make mapa` (scripts/mapa.py) a partir de los docstrings de módulo, los comentarios de cabecera de scripts/ y los comentarios `##` del Makefile. No editar a mano: `make check-docs` falla si queda desactualizado.

## services/core: paquete apexpulse

| Módulo | Descripción |
|---|---|
| `apexpulse` | Servicio core de ApexPulse: fuentes, modelo canónico, replay, motor de lecturas y API. |

## services/core: tests

| Módulo | Descripción |
|---|---|
| `test_paquete` | Verifica que el paquete se instala e importa desde el entorno de uv. |

## scripts

| Archivo | Descripción |
|---|---|
| `scripts/check_docs.py` | Verifica que la documentación y el CHANGELOG acompañen al cambio. |
| `scripts/check_private.sh` | Verifica que la capa privada no quede versionada en el repo público (ADR 0008). |
| `scripts/check_skills.py` | Verifica el formato de los skills y su correspondencia con la tabla de AGENTS.md. |
| `scripts/hook_stop.sh` | Hook Stop de Claude Code: corre make -s check-docs WARN=1 y devuelve los avisos al agente. |
| `scripts/mapa.py` | Genera docs/ai/mapa-codigo.md a partir de los docstrings, los scripts y el Makefile. |

## Targets de make

| Comando | Descripción |
|---|---|
| `make help` | Lista los targets disponibles |
| `make setup` | Instala dependencias de Python con uv y activa los hooks de git |
| `make check` | Todas las verificaciones |
| `make lint` | ruff: reglas de estilo y formato |
| `make typecheck` | mypy en modo estricto |
| `make test` | pytest |
| `make check-docs` | Docs, CHANGELOG y mapa al día con el cambio (WARN=1 solo avisa) |
| `make check-skills` | Formato de los skills y tabla de skills de AGENTS.md |
| `make check-private` | Falla si algo de la capa privada quedó versionado |
| `make mapa` | Regenera docs/ai/mapa-codigo.md |
