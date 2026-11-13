---
name: cambio-documentado
description: Cierra cualquier cambio en ApexPulse con la documentación, el CHANGELOG y el estado al día. Usar siempre que se modifique código en services/ o web/, configuración, compose.yaml, Makefile, infra/, skills o docs, antes de dar el trabajo por terminado o de abrir un PR.
---

# Cambio documentado

Todo cambio deja la documentación afectada actualizada en el mismo commit o PR.
Si no afecta documentación, se justifica por escrito.

## Pasos
1. Listar archivos cambiados: `git status --short` y `git diff --stat main...`.
2. Para cada archivo, aplicar la matriz y actualizar lo que corresponda. Si el
   documento destino todavía no existe, crearlo y sumarlo a docs/README.md.
3. Agregar la entrada en CHANGELOG.md, sección [Unreleased].
4. Si cambió una decisión que cuesta revertir, usar el skill nuevo-adr.
5. Si cambió la arquitectura o un ADR, actualizar docs/ai/contexto.md
   (200 líneas como máximo).
6. Si cambió la estructura de módulos, correr `make mapa`.
7. Si existe .private/estado.md, actualizarlo y commitearlo en el repo privado
   (`git -C .private ...`). Nunca mezclar archivos privados en un commit del
   repo público.
8. Correr `make check` (hoy incluye check-private; check-docs y check-skills se
   suman en H1 tarea 3). Debe pasar.

## Matriz: si tocás X, actualizá Y
| Cambio en                                    | Actualizar                                          |
|----------------------------------------------|-----------------------------------------------------|
| services/core/src/apexpulse/sources/         | docs/fuentes-de-datos.md, fixtures de contrato      |
| services/core/src/apexpulse/model/           | docs/modelo-de-eventos.md (versión), contexto.md    |
| readings/ o messages/es/                     | docs/lecturas.md, golden tests                      |
| api/                                         | docs/arquitectura.md (contrato de endpoints)        |
| web/src/styles/ o componentes base           | docs/diseno-visual.md                               |
| Makefile, compose.yaml, variables de entorno | docs/setup-local.md, tabla de comandos de AGENTS.md |
| infra/                                       | docs/arquitectura.md (nube), docs/runbook.md        |
| Un procedimiento repetible                   | El SKILL.md que lo describe                         |
| Un modo de falla nuevo                       | docs/runbook.md                                     |
| Alcance o hitos                              | docs/roadmap.md, .private/plan.md y ADR si aplica   |

## Formato de CHANGELOG (Keep a Changelog)
~~~markdown
## [Unreleased]
### Added
- Regla "parada barata bajo SC/VSC" con plantilla en español (#12).
### Changed
- Umbral de batalla sostenida: de 0,8 s a 1,0 s (ADR-0011).
### Fixed
- El adaptador OpenF1 reintenta ante 429 con backoff exponencial.
~~~
Categorías: Added, Changed, Deprecated, Removed, Fixed, Security.

## Cambios sin impacto en documentación
Válido solo para refactors internos sin cambio de comportamiento, tests o
formato. Se declara en el PR o en el mensaje del commit:
"Docs: sin impacto, refactor interno de store/ sin cambios de interfaz".

## Fuente de verdad
docs/README.md (índice) y .github/pull_request_template.md.
