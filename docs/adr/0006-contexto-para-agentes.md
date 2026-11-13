# 0006. El contexto para agentes se acota con AGENTS.md, skills y controles en CI

- Estado: Aceptado
- Fecha: 2026-11-09

## Contexto

El proyecto se desarrolla con Claude Code. Cada tarea no debería exigir releer toda la documentación, y cada cambio tiene que actualizar la documentación afectada en el mismo PR.

## Decisión

- AGENTS.md (120 líneas como máximo) es el índice siempre cargado; CLAUDE.md lo importa y agrega lo propio de Claude Code.
- docs/ai/contexto.md (200 líneas) y docs/ai/mapa-codigo.md (generado) acotan lo que hay que leer. El estado de trabajo vive en la capa privada (ADR 0008).
- Los procedimientos repetibles viven como skills en `.claude/skills/<nombre>/SKILL.md`, con el formato del estándar abierto Agent Skills.
- CI ejecuta `check-docs` y `check-skills`; un hook Stop de Claude Code avisa al terminar cada turno.

## Alternativas descartadas

- Un único CLAUDE.md extenso: se carga siempre, crece sin control y mezcla reglas con procedimientos.
- Confiar en que el agente recuerde actualizar la documentación: no es verificable.

## Consecuencias

- Un agente arranca leyendo menos de 400 líneas.
- Mantener los skills es parte de cada cambio (matriz del skill cambio-documentado).
- El formato estándar permite usar los mismos skills con otras herramientas si hiciera falta.
