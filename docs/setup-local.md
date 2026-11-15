# Setup local

Requisitos, comandos y verificaciones para trabajar en ApexPulse desde la compu: del clon limpio a `make check` en verde, y de ahí a una sesión reproducida por consola.

## Requisitos

| Herramienta | Versión | Para qué |
|-------------|---------|----------|
| git | 2.40 o superior | Repo y hooks |
| make | GNU Make 3.81 o superior | Puerta de entrada a todos los comandos |
| uv | 0.5 o superior | Entorno y dependencias de `services/core`; descarga Python 3.13 si falta |
| python3 | 3.11 o superior | Scripts de verificación de `scripts/` (solo biblioteca estándar) |

En macOS: `brew install uv`. En Linux: ver la documentación de uv.

## Primer arranque

```bash
git clone git@github.com:<usuario>/apexpulse.git
cd apexpulse
make setup    # uv sync --locked y git config core.hooksPath .githooks
make check    # todas las verificaciones, las mismas que corre CI
```

`make setup` baja Python 3.13 y las dependencias si faltan; `make check` corre unos 216 tests sin red y sin datos descargados (usan solo `fixtures/`). Los tiempos de un clon limpio medido están en [Tiempos](#tiempos).

`make help` lista los targets disponibles. El detalle de cada uno está en [ai/mapa-codigo.md](ai/mapa-codigo.md).

## Descargar una sesión

```bash
make fetch SESSION=2026-sao-paulo-r          # 8 requests a OpenF1; después, caché local
make fetch SESSION=2026-sao-paulo-r FORCE=1  # ignora la caché y vuelve a bajar
```

- El identificador es `<año>-<circuito>-<tipo>`. Circuitos válidos: `services/core/src/apexpulse/config/circuits.toml`. Tipos: `r`, `q`, `s`, `sq`, `fp1`, `fp2`, `fp3`.
- Se ejecuta desde la compu (IP residencial), nunca desde CI ni desde la nube.
- El crudo queda en `data/raw/<año>/<sesion>/openf1/` como JSONL zstd, con un `manifest.json`. La carrera de São Paulo 2026 ocupa unos 400 KB.
- `DATA_DIR=<ruta>` cambia el directorio de datos (por defecto `data/` en la raíz del repo). Sin make: `uv run --directory services/core python -m apexpulse fetch <id> --data-dir <ruta>`, o la variable `APEXPULSE_DATA_DIR`.
- Detalle del adaptador, límites y validación en [fuentes-de-datos.md](fuentes-de-datos.md#openf1); errores en [runbook.md](runbook.md#fuentes-de-datos).

## Normalizar una sesión

```bash
make normalize SESSION=2026-monaco-r   # requiere el crudo de make fetch; no usa la red
```

- Escribe `data/canonical/<sesion>.parquet` con los eventos canónicos v1 (unos 580 KB por carrera) e imprime los conteos por tipo y los cambios de estado de pista (SC, VSC, rojo) en UTC.
- Se puede repetir: misma entrada, mismo archivo. Después de cambiar el modelo o el normalizador, volver a correrlo.
- Sin make: `uv run --directory services/core python -m apexpulse normalize <id> --data-dir <ruta>`.
- Esquema en [modelo-de-eventos.md](modelo-de-eventos.md); mapeo desde OpenF1 en [fuentes-de-datos.md](fuentes-de-datos.md#mapeo-a-eventos-canónicos).

## Reproducir una sesión

```bash
make replay SESSION=2026-monaco-r SPEED=30              # 30 s de sesión por segundo real
make replay SESSION=2026-monaco-r NOWAIT=1 FROM_LAP=59  # sin esperas, desde la vuelta 59
make replay SESSION=2026-monaco-r NOWAIT=1 VERBOSE=1    # cada evento
```

- Requiere `data/canonical/<sesion>.parquet` (`make normalize`). No usa la red.
- `SPEED` es el multiplicador, mayor que 0 (por defecto 1). `NOWAIT=1` reproduce sin esperar e ignora `SPEED`. `FROM_LAP=<n>` empieza en la vuelta `n` del líder.
- Sale una línea por hecho, con hora UTC y vuelta en curso del líder: un marcador por vuelta, los cambios de estado de pista, los mensajes de dirección de carrera (sin traducir y sin las banderas azules), las paradas con detención y las lecturas del motor (`LECTURA`). `VERBOSE=1` suma vueltas, posiciones, intervalos, stints, clima, pilotos, banderas azules y pasadas por el pit lane sin detención.
- Ctrl-C corta con código 130. Cortar la salida con `| head` no es un error.
- Sin make: `uv run --directory services/core python -m apexpulse replay <id> --speed 30 [--no-wait] [--from-lap N] [--verbose] --data-dir <ruta>`.
- Diseño del reloj, del seek y de la convención de vuelta en [arquitectura.md](arquitectura.md#reloj-de-replay).

Ejemplo real (`make replay SESSION=2026-monaco-r NOWAIT=1 FROM_LAP=60`, recortado):

```text
2026-monaco-r · Mónaco · openf1 · sin espera · hora UTC
── Vuelta 60 · lidera ANT
14:19:45  v60  DIRECCIÓN  YELLOW IN TRACK SECTOR 18
14:20:02  v60  DIRECCIÓN  SAFETY CAR DEPLOYED
14:20:02  v60  PISTA      SC (SAFETY CAR DEPLOYED)
── Vuelta 61 · lidera ANT
14:21:26  v61  PARADA     HAM 8,6 s detenido · 31,2 s en pit lane
14:21:34  v61  PARADA     ALO 4,3 s detenido · 26,3 s en pit lane
14:21:52  v61  DIRECCIÓN  ALL CARS THROUGH THE PIT LANE
```

Con el motor de lecturas (por defecto en `make replay`), cada lectura sale como una línea `LECTURA`, debajo del evento que la dispara:

```text
14:21:26  v61  PARADA     HAM 8,6 s detenido · 31,2 s en pit lane
14:21:26  v61  LECTURA    HAM para bajo Safety Car en la vuelta 61: 8,6 s detenido y 31,2 s en pit lane.
```

Reglas, umbrales y textos en [lecturas.md](lecturas.md).

## Recortar un fixture

```bash
make fixture SESSION=2026-monaco-r DESDE=2026-06-07T14:15 HASTA=2026-06-07T15:15 LAPS=57-70
```

- Requiere el crudo (`make fetch`); no usa la red. Sobrescribe `fixtures/sessions/<id>/openf1/` (menos de 2 MB por sesión): revisar el diff antes de commitear.
- `DESDE` y `HASTA` son instantes UTC si no llevan zona; `LAPS` es el rango de vueltas del líder. `SALIDA=<dir>` cambia el destino y `VACIAR=<endpoints>` (por ejemplo `intervals,position,weather`) escribe esos endpoints vacíos, para un fixture de carrera completa sin los pesados. Criterio de recorte y arrastre en [fuentes-de-datos.md](fuentes-de-datos.md#recorte-de-fixtures).
- Sin make: `uv run --directory services/core python -m apexpulse fixture <id> --desde <iso> --hasta <iso> --vueltas <a>-<b> --salida <dir> --data-dir <ruta>`.

## Tests y golden

```bash
make test                                        # todo pytest, sin red
make golden-update                               # regraba tests/golden con la salida actual
make golden-update SESSION=2026-monaco-r         # una sola sesión
```

- Los tests viven en `services/core/tests/` y usan solo `fixtures/`; los sockets están bloqueados. Con las sesiones completas en `data/canonical` (después de `make fetch` y `make normalize`) se suman unos casos extra que en CI se saltean.
- `tests/test_golden.py` compara la salida de la regla `cheap_stop` sobre Mónaco, Australia y São Paulo con `tests/golden/<sesion>.cheap_stop.json`. Si cambia un texto, un umbral o el normalizador, el test falla y apunta a `make golden-update`.
- `make golden-update` solo reescribe los golden y muestra `git diff --stat`. Revisar el diff completo (`git diff services/core/tests/golden`) y poner el motivo en el mensaje del commit. Nunca se regenera para "hacer pasar" un test sin entender la diferencia.
- `tests/test_propiedades.py` (causalidad, una lectura por pareja y stint, seek, vuelta mínima) y `tests/test_pipeline.py` (dos corridas desde los fixtures dan salida idéntica) no usan golden: comparan la corrida contra sí misma o contra la secuencia completa.
- Qué garantiza cada archivo y por qué `undercut_window` no tiene golden todavía: [lecturas.md](lecturas.md#golden-y-propiedades).

## Verificaciones

| Target | Qué verifica | Falla cuando |
|--------|--------------|--------------|
| `make lint` | ruff sobre `services/core` y `scripts/` | Hay errores de estilo, imports desordenados, módulos sin docstring o archivos sin formatear |
| `make typecheck` | mypy en modo estricto sobre `src/`, `tests/` y `scripts/` | Falta una anotación o un tipo no cierra |
| `make test` | pytest en `services/core/tests`: unitarios, contrato, golden, propiedades y pipeline | Falla un test; un golden que cambió falla con el aviso de `make golden-update` |
| `make check-docs` | Documentación al día con el cambio | Ver la tabla siguiente |
| `make check-skills` | Formato de `.claude/skills/*/SKILL.md` y tabla de skills de `AGENTS.md` | Falta `name` o `description`, el nombre no coincide con la carpeta, o la tabla no refleja los skills existentes |
| `make check-private` | Capa privada fuera del repo público (ADR 0008) | `.private/` o `CLAUDE.local.md` están en el índice |

Reglas de `make check-docs`. El cambio se calcula contra el merge-base con `origin/main` (o `main`), más los archivos modificados y nuevos sin commitear.

| Regla | Ejemplo de error |
|-------|------------------|
| Todo cambio agrega una entrada en `CHANGELOG.md` | `Falta la entrada en CHANGELOG.md, sección [Unreleased].` |
| Matriz del skill cambio-documentado | `Cambió Makefile: actualizar docs/setup-local.md o AGENTS.md.` |
| Enlaces relativos en Markdown | `docs/README.md:12: enlace roto a lecturas.md` |
| Límites de líneas: `AGENTS.md` 120, `docs/ai/contexto.md` 200 | `AGENTS.md tiene 131 líneas; el límite es 120.` |
| Mapa de código generado | `docs/ai/mapa-codigo.md está desactualizado. Correr: make mapa` |

Si el cambio no afecta documentación, se declara en el mensaje de un commit o en el cuerpo del PR con un motivo real, y check-docs omite las dos primeras reglas:

```text
Docs: sin impacto, refactor interno de store/ sin cambios de interfaz
```

Variables: `WARN=1` informa los problemas y sale con 0; `BASE_REF=<ref>` cambia la base de comparación; `PR_BODY` recibe el cuerpo del PR en CI.

## Hooks

| Hook | Archivo | Qué hace |
|------|---------|----------|
| pre-commit de git | `.githooks/pre-commit` | Corre `make -s check-private`; se activa con `make setup` |
| Stop de Claude Code | `.claude/settings.json` y `scripts/hook_stop.sh` | Corre `make -s check-docs WARN=1` al terminar cada turno; si hay avisos, se los devuelve al agente una vez (sale con 2) y en el turno siguiente solo informa |

## CI

`.github/workflows/ci.yml` corre en cada PR (también al editar su descripción) y en cada push a `main`:

- Job `python`: `uv sync --locked`, `make lint`, `make typecheck` y `make test`.
- Job `docs`: `make check-private`, `make check-skills` y `make check-docs` con `BASE_REF` igual a la rama base del PR, o al commit anterior en un push.

CI no descarga datos de ninguna fuente: los tests usan solo fixtures versionados en `fixtures/sessions/` y `services/core/tests/conftest.py` bloquea los sockets durante los tests.

## Tiempos

Medido el 2026-11-15 en un clon limpio de la rama h1/t8-golden, en macOS con uv ya instalado y su caché caliente (Python 3.13 y wheels ya descargados). En una compu sin caché, `make setup` suma la descarga de Python y de las dependencias.

TIEMPOS_AQUI

## Problemas comunes

| Síntoma | Causa | Solución |
|---------|-------|----------|
| `error: The lockfile at uv.lock needs to be updated` | Cambió `pyproject.toml` sin regenerar el lock | `uv lock --directory services/core` y commitear `uv.lock` |
| `make: uv: No such file or directory` | uv no instalado | Instalar uv (ver Requisitos) |
| `make replay` responde `no existe data/canonical/...` | Falta normalizar la sesión | `make normalize SESSION=<id>` (y antes `make fetch` si no hay crudo) |
| `make replay` responde `eventos fuera de orden` o `esquema canónico 2.x` | Parquet generado por otra versión del normalizador | `make normalize SESSION=<id>` |
| `make fetch` responde `queda disponible desde ...` | La sesión no terminó o terminó hace menos de 30 minutos | Reintentar después; otros errores de descarga en [runbook.md](runbook.md#fuentes-de-datos) |
| `make test` falla en `test_golden.py` con "la salida cambió" | Cambió un texto, un umbral, el normalizador o un fixture | Entender la diferencia; si es intencional, `make golden-update`, revisar el diff y justificarlo en el commit |
| `test_golden.py` falla con "falta el golden" | Sesión nueva sin su archivo en `tests/golden/` | `make golden-update SESSION=<id>` y revisar el archivo nuevo |
| check-docs marca archivos que no tocaste | La rama local `main` está atrasada | `git fetch origin` para actualizar `origin/main` |
