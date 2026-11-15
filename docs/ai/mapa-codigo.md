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
| `apexpulse.readings` | Motor de lecturas: reglas determinísticas sobre el replay, con conclusiones en español. |
| `apexpulse.readings.cheap_stop` | Regla `cheap_stop`: parada real bajo Safety Car o VSC. |
| `apexpulse.readings.config` | Carga y validación de config/readings.toml y config/mensajes_es.toml. |
| `apexpulse.readings.engine` | Motor de lecturas: aplica las reglas a cada evento, en el orden del replay. |
| `apexpulse.readings.format` | Formato de números de los textos: coma decimal. |
| `apexpulse.readings.model` | Modelo de una lectura: una conclusión con su evidencia numérica y su texto en español. |
| `apexpulse.readings.stops` | Seguimiento de paradas reales: la memoria que comparten las reglas. |
| `apexpulse.readings.undercut` | Regla `undercut_window`: un auto lleva varias vueltas pegado al de adelante. |
| `apexpulse.replay` | Reloj de replay: reproduce una sesión canónica con velocidad, pausa y seek. |
| `apexpulse.replay.clock` | Reloj inyectable del replay: el del sistema para la consola y uno falso para los tests. |
| `apexpulse.replay.console` | Salida del replay por consola: una línea por hecho relevante, con hora UTC y vuelta del líder. |
| `apexpulse.replay.player` | Reproductor de una sesión canónica con velocidad variable, pausa y seek. |
| `apexpulse.replay.state` | Estado acumulado de la carrera: un fold puro de los eventos canónicos en orden. |
| `apexpulse.session_id` | Identificador de sesión `<año>-<circuito>-<tipo>` y tabla de circuitos. |
| `apexpulse.sources` | Adaptadores de fuente: lo único del código que conoce el formato de cada fuente (ADR 0002). |
| `apexpulse.sources.base` | Contrato común de los adaptadores de fuente: descarga del crudo y normalización a eventos v1. |
| `apexpulse.sources.openf1` | Adaptador de OpenF1: descarga histórica con caché local, límite de tasa y reintentos. |
| `apexpulse.sources.openf1_normalize` | Normalizador de OpenF1: del crudo en data/raw a eventos canónicos v1. |
| `apexpulse.sources.openf1_recorte` | Recorte de una sesión de OpenF1 a una ventana, para armar fixtures versionados. |
| `apexpulse.sources.ratelimit` | Límite de tasa por ventanas deslizantes, con estado opcional compartido entre ejecuciones. |
| `apexpulse.sources.rawstore` | Escritura y lectura del crudo en JSONL comprimido con zstd (ADR 0005). |
| `apexpulse.sources.trackstatus` | Deriva el estado de pista (SC, VSC, rojo) de los mensajes de dirección de carrera. |

## services/core: tests

| Módulo | Descripción |
|---|---|
| `conftest` | Fixtures compartidos: red bloqueada, reloj falso y OpenF1 simulado con respuestas grabadas. |
| `contract.test_openf1` | Test de contrato del adaptador OpenF1 contra respuestas grabadas de 2026-sao-paulo-r. |
| `contract.test_openf1_normalize` | Test de contrato del normalizador OpenF1 y del endpoint race_control con 2026-monaco-r. |
| `helpers` | Ayudas de los tests de salida completa: pipeline desde fixtures, serialización y golden. |
| `test_cli` | Tests de la línea de comandos (sin red: solo caminos que no llegan a la fuente). |
| `test_golden` | Golden de `cheap_stop` sobre las tres carreras con fixtures y los casos que lo explican. |
| `test_model` | Tests del modelo canónico v1.1: validación de eventos, orden y Parquet. |
| `test_paquete` | Verifica que el paquete se instala e importa desde el entorno de uv. |
| `test_pipeline` | Pipeline completo desde los fixtures: dos corridas independientes dan salida idéntica. |
| `test_propiedades` | Propiedades de `undercut_window` sobre carreras reales (fixtures) y, si existen, completas. |
| `test_ratelimit` | Tests del límite de tasa por ventanas deslizantes. |
| `test_rawstore` | Tests del crudo en JSONL zstd. |
| `test_readings` | Tests del motor de lecturas: paradas reales, `cheap_stop`, `undercut_window` y causalidad. |
| `test_recorte` | Tests del recorte de fixtures de OpenF1 con un crudo sintético de dos pilotos. |
| `test_replay` | Tests del reloj de replay con 2026-monaco-r como caso principal, sin esperas reales. |
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
| `make replay` | Reproduce una sesión por consola (SESSION=<id> [SPEED=<n>] [NOWAIT=1] [FROM_LAP=<n>] [VERBOSE=1]) |
| `make fixture` | Recorta el crudo a una ventana y regraba fixtures/sessions (SESSION=<id> DESDE=<iso> HASTA=<iso> LAPS=<a>-<b> [SALIDA=<dir>] [VACIAR=<endpoints>]) |
| `make golden-update` | Regraba tests/golden con la salida actual y muestra el diff (SESSION=<id> para una sola sesión) |
