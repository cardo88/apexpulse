# Contexto para agentes

Digest de la arquitectura y de las decisiones vigentes. Límite: 200 líneas. Se actualiza con cada ADR o cambio de arquitectura (skill cambio-documentado). Última actualización: 2026-11-14.

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

- Ocho eventos inmutables con `t` en UTC: lap, stint, pit, position, interval, race_control, track_status y weather (model/events.py, versión `SCHEMA_VERSION` 1.0).
- Un Parquet ancho por sesión en data/canonical/<sesion>.parquet, orden total con `sort_key` y salida determinística (`make normalize`).
- `track_status` se deriva de race_control (sources/trackstatus.py). `NEUTRALIZED` = SC, SC_ENDING, VSC y VSC_ENDING; el rojo queda aparte.
- `pit.stationary_s` null es una pasada por el pit lane, no una parada.
- Detalle en docs/modelo-de-eventos.md.

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
