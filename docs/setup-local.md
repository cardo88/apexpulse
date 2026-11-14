# Setup local

Requisitos, comandos y verificaciones para trabajar en ApexPulse desde la compu. Se completa en H1 tarea 8 con el replay de sesiones.

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

## Verificaciones

| Target | Qué verifica | Falla cuando |
|--------|--------------|--------------|
| `make lint` | ruff sobre `services/core` y `scripts/` | Hay errores de estilo, imports desordenados, módulos sin docstring o archivos sin formatear |
| `make typecheck` | mypy en modo estricto sobre `src/`, `tests/` y `scripts/` | Falta una anotación o un tipo no cierra |
| `make test` | pytest en `services/core/tests` | Falla un test |
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

## Problemas comunes

| Síntoma | Causa | Solución |
|---------|-------|----------|
| `error: The lockfile at uv.lock needs to be updated` | Cambió `pyproject.toml` sin regenerar el lock | `uv lock --directory services/core` y commitear `uv.lock` |
| `make: uv: No such file or directory` | uv no instalado | Instalar uv (ver Requisitos) |
| `make fetch` responde `queda disponible desde ...` | La sesión no terminó o terminó hace menos de 30 minutos | Reintentar después; otros errores de descarga en [runbook.md](runbook.md#fuentes-de-datos) |
| check-docs marca archivos que no tocaste | La rama local `main` está atrasada | `git fetch origin` para actualizar `origin/main` |
