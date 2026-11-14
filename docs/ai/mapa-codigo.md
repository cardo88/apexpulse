# Mapa de código

Generado por `make mapa` (scripts/mapa.py) a partir de los docstrings de módulo, los comentarios de cabecera de scripts/ y los comentarios `##` del Makefile. No editar a mano: `make check-docs` falla si queda desactualizado.

## services/core: paquete apexpulse

| Módulo | Descripción |
|---|---|
| `apexpulse` | Servicio core de ApexPulse: fuentes, modelo canónico, replay, motor de lecturas y API. |
| `apexpulse.__main__` | Punto de entrada de `python -m apexpulse`. |
| `apexpulse.cli` | Línea de comandos de apexpulse; la invocan los targets de make. |
| `apexpulse.model` | Modelo canónico de eventos v1 y su persistencia en Parquet (ADR 0002 y 0005). |
| `apexpulse.model.events` | Eventos canónicos v1: el contrato entre los adaptadores de fuente y el resto del sistema. |
| `apexpulse.model.parquet` | Persistencia de los eventos canónicos en Parquet: una tabla ancha por sesión (ADR 0005). |
| `apexpulse.session_id` | Identificador de sesión `<año>-<circuito>-<tipo>` y tabla de circuitos. |
| `apexpulse.sources` | Adaptadores de fuente: lo único del código que conoce el formato de cada fuente (ADR 0002). |
| `apexpulse.sources.base` | Contrato común de los adaptadores de fuente: descarga del crudo y normalización a eventos v1. |
| `apexpulse.sources.openf1` | Adaptador de OpenF1: descarga histórica con caché local, límite de tasa y reintentos. |
| `apexpulse.sources.openf1_normalize` | Normalizador de OpenF1: del crudo en data/raw a eventos canónicos v1. |
| `apexpulse.sources.ratelimit` | Límite de tasa por ventanas deslizantes, con estado opcional compartido entre ejecuciones. |
| `apexpulse.sources.rawstore` | Escritura y lectura del crudo en JSONL comprimido con zstd (ADR 0005). |
| `apexpulse.sources.trackstatus` | Deriva el estado de pista (SC, VSC, rojo) de los mensajes de dirección de carrera. |

## services/core: tests

| Módulo | Descripción |
|---|---|
| `conftest` | Fixtures compartidos: red bloqueada, reloj falso y OpenF1 simulado con respuestas grabadas. |
| `contract.test_openf1` | Test de contrato del adaptador OpenF1 contra respuestas grabadas de 2026-sao-paulo-r. |
| `contract.test_openf1_normalize` | Test de contrato del normalizador OpenF1 y del endpoint race_control con 2026-monaco-r. |
| `test_cli` | Tests de la línea de comandos (sin red: solo caminos que no llegan a la fuente). |
| `test_model` | Tests del modelo canónico v1: validación de eventos, orden y Parquet. |
| `test_paquete` | Verifica que el paquete se instala e importa desde el entorno de uv. |
| `test_ratelimit` | Tests del límite de tasa por ventanas deslizantes. |
| `test_rawstore` | Tests del crudo en JSONL zstd. |
| `test_session_id` | Tests del identificador de sesión y de la tabla de circuitos. |
| `test_trackstatus` | Tests de la derivación del estado de pista a partir de mensajes de dirección de carrera. |

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
| `make fetch` | Descarga y cachea una sesión de OpenF1 (SESSION=<id>; FORCE=1 ignora la caché) |
| `make normalize` | Genera los eventos canónicos v1 en data/canonical (SESSION=<id>; requiere make fetch) |
