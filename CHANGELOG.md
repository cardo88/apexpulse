# Changelog

Todos los cambios relevantes de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

## [Unreleased]

## [0.1.0] - 2026-11-15

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
- Modelo canónico de eventos v1 (`apexpulse.model`, esquema 1.0): ocho eventos inmutables en Pydantic con instante UTC (lap, stint, pit, position, interval, race_control, track_status y weather), orden total y determinístico, y persistencia en un Parquet ancho por sesión.
- Normalizador de OpenF1 (`sources/openf1_normalize.py`) y `normalize` en el contrato `SourceAdapter`.
- Estado de pista derivado de los mensajes de dirección de carrera (`sources/trackstatus.py`): SC, VSC, sus finales, bandera roja con reanudación y fin de sesión.
- `make normalize SESSION=<id>` (`python -m apexpulse normalize`), que escribe `data/canonical/<sesion>.parquet`.
- Fixture `2026-monaco-r` con el tramo del SC con paradas en boxes y la bandera roja, y tests de contrato de `race_control` y de la normalización.
- `docs/modelo-de-eventos.md` y tabla de mapeo de OpenF1 a eventos canónicos en `docs/fuentes-de-datos.md`.
- Endpoint `drivers` de OpenF1 en el adaptador, con su esquema, caché y test de contrato, y fixtures `drivers.json` de `2026-monaco-r` y `2026-sao-paulo-r`.
- Evento canónico `driver` (`DriverInfo`): número del auto, código de 3 letras (`acronym`), nombre y equipo, con `t` igual al inicio de la sesión. Columnas `acronym`, `name` y `team` en el Parquet.
- Reloj de replay (`apexpulse.replay`): reloj inyectable (`SystemClock` y `FakeClock`), reproducción de `data/canonical/<sesion>.parquet` en el orden del normalizador, con multiplicador de velocidad, modo sin espera, pausa, `seek`, `seek_lap` y recorte opcional de huecos (`max_gap_s`).
- Estado acumulado de la carrera (`RaceState`) como fold puro de los eventos, con la convención de vuelta en curso del líder y el líder como piloto en posición 1.
- `make replay SESSION=<id> [SPEED=<n>] [NOWAIT=1] [FROM_LAP=<n>] [VERBOSE=1]` (`python -m apexpulse replay`), con salida por consola en hora UTC.
- `make fixture SESSION=<id> DESDE=<iso> HASTA=<iso> LAPS=<a>-<b>` (`sources/openf1_recorte.py`): recorta el crudo a una ventana sin modificar registros y arrastra, por piloto, el último registro anterior a la ventana y a la largada de `position` e `intervals`, el último stint previo y la última vuelta completada previa.
- Fixture `2026-sao-paulo-r` como ventana de las vueltas 12 a 20 (21 pasadas por boxes, 3 sin `stop_duration`); el mínimo de tres registros por endpoint queda en `fixtures/contract/2026-sao-paulo-r/` para el test de contrato.
- Tests de `test_trackstatus.py` con los textos reales de OpenF1 para el VSC.
- Motor de lecturas (`apexpulse.readings`): `Engine`, `Reading` con evidencia numérica y texto en español, configuración validada (`config/readings.toml`, umbrales sin calibrar) y plantillas (`config/mensajes_es.toml`). Es causal y su estado es un fold de los eventos: tras un seek produce las mismas lecturas que la reproducción continua, sin repetir las anteriores. `Replay` acepta un `Observer` y `Step` trae `readings`; `make replay` imprime las líneas `LECTURA`.
- Seguimiento de paradas reales (`readings/stops.py`): `stationary_s` no nulo, o stint nuevo en la vuelta de la pasada o la siguiente con juego de neumáticos distinto, con confirmación diferida que vence sin emitir.
- Regla `cheap_stop`: parada real bajo SC o VSC, con evidencia observable (sin afirmar ahorro de tiempo).
- Regla `undercut_window`: auto a 2 s o menos del de adelante con neumático viejo durante 2 vueltas, con guardas contra autos doblados, vueltas de boxes y paradas recientes.
- `docs/lecturas.md`: catálogo de reglas, definición de parada real, umbrales sin calibrar y la medición de las 15 parejas confundidas. La regla de undercut no conoce las vueltas restantes.
- Skill `nueva-lectura`.
- Fixture `2026-australia-r` (tres VSC, vueltas 12 a 35, 1,49 MiB) y fixture de carrera completa `fixtures/contract/2026-sao-paulo-r-paradas/` solo con `pit`, `stints`, `laps` y `race_control`.
- `make fixture` con `SALIDA=<dir>` y `VACIAR=<endpoints>`.
- Golden tests de `cheap_stop` sobre Mónaco, Australia y São Paulo (`services/core/tests/golden/`, `tests/test_golden.py`): Mónaco 8 lecturas, Australia con los VSC de las vueltas 12 (10) y 18 (4) y el de la 34 (1, de borde: pasada con el estado en `VSC_ENDING`), São Paulo 0.
- `make golden-update [SESSION=<id>]`: regraba los golden y muestra el diff; el test normal nunca escribe (`pytest --golden-update`).
- Propiedades de `undercut_window` (`tests/test_propiedades.py`): causalidad, una lectura por pareja y stint, estabilidad tras seek y respeto de la vuelta mínima, sobre los fixtures y, si están, sobre las carreras completas.
- Test de pipeline completo desde los fixtures (`tests/test_pipeline.py`): dos corridas independientes dan los mismos avisos, bytes de Parquet, lecturas, consola y salida de la CLI.
- Guarda `[undercut_window] min_lap` (por defecto 5, sin calibrar) y evidencia `vuelta_perseguidor`; `undercut_window` pasa a la versión 2. No cambia la salida de las tres carreras de prueba.
- Test que cubre el aviso del normalizador cuando omite un stint sin `tyre_age_at_start`.
- `docs/setup-local.md` completo (tests, golden, tiempos de un clon limpio) y `docs/lecturas.md` con los casos verificados, el análisis de las lecturas de las primeras vueltas y la sección de golden y propiedades.

### Changed
- Dependencias de `services/core`: se suman `pydantic` y `pyarrow`.
- Los fixtures recortados escriben un registro por línea en vez de un campo por línea: el mismo contenido pesa alrededor de un 15 % menos y el diff de git se lee por registro.
- `fixtures/sessions/2026-sao-paulo-r/` pasa de tres registros por endpoint a una ventana reproducible; los tests de contrato del adaptador usan `fixtures/contract/2026-sao-paulo-r/`.
- El replay pliega sin emitir los eventos anteriores a la largada que trae un fixture recortado (posiciones de la grilla).
- `FakeClock` de los tests pasa de `tests/conftest.py` a `apexpulse.replay.clock`; conftest lo reexporta y los tests del límite de tasa no cambian.
- Modelo canónico: esquema 1.1 (versión menor). Los archivos 1.0 se siguen leyendo; renormalizar para tener los eventos `driver`.
- `make fetch` con un manifiesto al que le faltan endpoints baja solo esos, en lugar de descargar toda la sesión otra vez.
- El normalizador de OpenF1 avisa y sigue si el crudo no tiene `drivers`.
- La tabla de comandos de `AGENTS.md` y el skill `sesion-replay` usan `make golden-update` en lugar del `make golden` previsto; el skill `nueva-lectura` describe el golden y las propiedades.

### Fixed
- La edad del neumático de las lecturas cuenta la vuelta que se acaba de completar (un stint que empieza en la vuelta 1 tiene 10 vueltas de uso al completar la 10).
- El estado de pista `VSC` nunca se derivaba: OpenF1 publica `VSC DEPLOYED` y `VSC ENDING` (14 de las 20 carreras 2026) y `sources/trackstatus.py` solo reconocía `VIRTUAL SAFETY CAR ...`. Ahora acepta ambos textos.
- Los fixtures recortados de `2026-monaco-r` no traían quién lidera ni la distancia de cada auto (OpenF1 publica `position` e `intervals` solo al cambiar): la consola decía `lidera ---`. El recorte ahora arrastra el último registro previo de cada piloto.
- `make check-private` ya no falla en un clon sin `.private/` (por ejemplo, en CI).
