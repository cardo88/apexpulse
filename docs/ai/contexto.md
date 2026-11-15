# Contexto para agentes

Digest de la arquitectura y de las decisiones vigentes. Límite: 200 líneas. Se actualiza con cada ADR o cambio de arquitectura (skill cambio-documentado). Última actualización: 2026-11-15.

## Producto

- Lectura de carrera de F1 en español: conclusiones con evidencia numérica, no datos crudos.
- Audiencia: aficionados hispanohablantes que miran la carrera; también funciona como portfolio técnico.
- Salidas: vista "En carrera" (replay ahora, vivo en H7) y post-carrera estático de una página.

## Principios, en orden de peso

1. Identidad visual propia, no un template.
2. Diferenciación sostenida: interpretación en español y bajo consumo de datos.
3. Un MVP chico que funcione antes que un diseño perfecto.

## Arquitectura en una línea

Adaptadores por fuente, modelo canónico v1, reloj de replay, motor de lecturas, API (REST y SSE) y web Astro. Datos en archivos bajo ./data. Detalle en docs/arquitectura.md.

## Modelo canónico v1

- Nueve eventos inmutables con `t` en UTC: driver, lap, stint, pit, position, interval, race_control, track_status y weather (model/events.py, versión `SCHEMA_VERSION` 1.1).
- `driver` lleva el código de 3 letras (`acronym`), el nombre y el equipo de cada auto, con `t` = inicio de la sesión. Las lecturas toman el código de ahí, no de una tabla propia.
- Un Parquet ancho por sesión en data/canonical/<sesion>.parquet, orden total con `sort_key` y salida determinística (`make normalize`).
- `track_status` se deriva de race_control (sources/trackstatus.py). `NEUTRALIZED` = SC, SC_ENDING, VSC y VSC_ENDING; el rojo queda aparte.
- `pit.stationary_s` null es una pasada por el pit lane, no una parada.
- Detalle en docs/modelo-de-eventos.md.

## Replay

- `apexpulse.replay`: reloj inyectable (`Clock`, `SystemClock`, `FakeClock`), `Replay` sobre el Parquet canónico y `RaceState` como fold puro (`apply`). `make replay SESSION=<id> SPEED=<n>`, con `NOWAIT=1` y `FROM_LAP=<n>`.
- El orden de emisión es el de `sort_key`: el replay valida, no reordena. Los eventos con el mismo `t` salen en un lote.
- El seek deja el estado igual a reproducir hasta ese instante y no emite lo salteado. La posición inicial es `SessionMeta.start`.
- Vuelta N = vuelta en curso del líder = máximo de vueltas completadas + 1, fija desde la bandera a cuadros. Coincide con el `lap` de los mensajes de la FIA. El líder que se nombra es el de P1.
- Tests con `FakeClock`, sin esperas reales. `Replay` acepta un `Observer` (el motor de lecturas) que se reinicia y re-pliega con el seek. Detalle en docs/arquitectura.md#reloj-de-replay.

## Motor de lecturas

- `apexpulse.readings`: `Engine` + reglas `cheap_stop` (parada real bajo SC/VSC) y `undercut_window`. `make replay` imprime las lecturas (`LECTURA`). Detalle y umbrales en docs/lecturas.md.
- Golden: `cheap_stop` tiene golden por sesión en services/core/tests/golden/ (`make golden-update`); `undercut_window` se cubre con propiedades hasta calibrar. Detalle en docs/lecturas.md.
- Causal y determinístico; el estado del motor es un fold de los eventos y se reinicia y re-pliega con el seek, igual que `RaceState`. Se engancha al replay por el protocolo `Observer`.
- Parada real: `stationary_s` no nulo, o stint nuevo en la vuelta de la pasada o la siguiente con juego de neumáticos distinto (confirmación diferida que vence sin emitir). OpenF1 abre el stint en la vuelta de la pasada (Mónaco) o en la siguiente (São Paulo) y bajo SC parte uno por pasada: no alcanza solo `stop_duration` ni solo el stint.
- Umbrales en config/readings.toml, todos `calibrated = false` (incluida la guarda `min_lap` de undercut). Textos en config/mensajes_es.toml: sin afirmaciones de ahorro de tiempo. La regla de undercut no conoce las vueltas restantes.
- OpenF1 publica el VSC como `VSC DEPLOYED` y `VSC ENDING`.
- Fixtures recortados con `make fixture` (arrastra el último registro previo de cada piloto): Mónaco (SC), São Paulo (vueltas 12 a 20) y Australia (tres VSC).

## Decisiones vigentes

| ADR | Decisión |
|-----|----------|
| 0001 | Lectura de carrera en español; overlays y pronósticos quedan como extensiones |
| 0002 | Modelo canónico de eventos v1; nada fuera de sources/ conoce el formato de una fuente |
| 0003 | MVP solo con replay; vivo en H7 |
| 0004 | SSE en local; en la nube, JSON cada 2 a 5 s con polling cacheado |
| 0005 | Crudo JSONL zstd, canónico Parquet, consultas con DuckDB |
| 0006 | AGENTS.md, digest, estado, mapa generado, skills y check-docs en CI |
| 0007 | Licencia MIT; solo datos derivados; sin F1 TV; sin marcas oficiales en la UI |
| 0008 | Capa privada en .private/: repo anidado, ignorado por el público y verificado por make check-private |

Pendientes: 0009 ingesta residencial (H7) y 0010 nube objetivo (H6).

## Restricciones duras

- Nada en la nube ni en CI habla con F1 Live Timing ni con su archivo estático.
- Sin credenciales de F1 TV y sin publicar el crudo.
- Lecturas determinísticas, cubiertas por golden tests.
- .private/ y CLAUDE.local.md nunca se versionan en el repo público.
- Temporada 2026: 11 equipos, 22 autos y sin DRS. Las reglas usan umbrales de gap, no estados de DRS.

## Fuentes

- OpenF1: primaria del MVP; histórico desde 2023; 3 req/s y 30 req/min. Adaptador en sources/openf1.py con caché en data/raw y límite compartido en data/state (`make fetch`); normalizador en sources/openf1_normalize.py (`make normalize`).
- Archivo estático de Live Timing: segunda fuente, mismo formato que el vivo, solo desde IP residencial.
- Jolpica-F1: contexto (standings y resultados).

Detalle en docs/fuentes-de-datos.md.

## Stack

Python 3.13 con uv, httpx, zstandard, Pydantic v2, FastAPI con SSE, JSONL zstd, Parquet y DuckDB, Astro con islas Svelte y TypeScript, SVG propio con d3-scale y d3-shape, Docker Compose y Makefile, GitHub Actions y Terraform.

## Convenciones

- Identificador de sesión: `<año>-<circuito>-<tipo>`, por ejemplo `2026-sao-paulo-r`.
- Textos de lecturas: español neutro, presente, voz activa, códigos de piloto de 3 letras, coma decimal con unidad (`19,8 s`).
- Commits: Conventional Commits. Versiones: SemVer, una MINOR por hito.

## Glosario

- Lectura: conclusión producida por una regla, con vuelta, pilotos, evidencia y texto.
- Undercut: parar antes que el rival para aprovechar el neumático nuevo y salir delante.
- Overcut: quedarse afuera más vueltas para ganar la posición con aire limpio.
- Parada barata: parada bajo Safety Car o VSC, donde se pierde menos tiempo relativo.
- Stint: tramo de carrera con un mismo juego de neumáticos.
- Degradación: pérdida de ritmo por vuelta a medida que se gasta el neumático.
- Gap e intervalo: distancia en segundos al líder y al auto de adelante.
- SC y VSC: Safety Car y Virtual Safety Car.
- Golden test: compara la salida completa contra una salida esperada versionada.
