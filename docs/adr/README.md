# Decisiones de arquitectura (ADR)

Formato corto: contexto, decisión, alternativas descartadas y consecuencias. Para registrar una nueva, usar el skill `nuevo-adr` y la [plantilla](template.md).

| ADR | Título | Estado | Fecha |
|-----|--------|--------|-------|
| [0001](0001-lectura-de-carrera-en-espanol.md) | El producto es una lectura de carrera en español | Aceptado | 2026-11-09 |
| [0002](0002-modelo-canonico-de-eventos.md) | Un modelo canónico de eventos separa fuentes y motor | Aceptado | 2026-11-09 |
| [0003](0003-mvp-solo-con-replay.md) | El MVP funciona solo con replay | Aceptado | 2026-11-09 |
| [0004](0004-sse-y-polling-cacheado.md) | SSE en local y polling cacheado en la nube | Aceptado | 2026-11-09 |
| [0005](0005-datos-en-archivos.md) | Los datos viven en archivos, sin base de datos servidor | Aceptado | 2026-11-09 |
| [0006](0006-contexto-para-agentes.md) | El contexto para agentes se acota con AGENTS.md, skills y controles en CI | Aceptado | 2026-11-09 |
| [0007](0007-licencia-mit-y-postura-legal.md) | Licencia MIT y postura legal de proyecto no oficial | Aceptado | 2026-11-09 |
| [0008](0008-capa-privada-en-repo-anidado.md) | La información privada vive en un repo anidado en .private/ | Aceptado | 2026-11-12 |

Números reservados:

- 0009: ingesta en vivo desde IP residencial (se registra en H7).
- 0010: nube objetivo, AWS con Terraform o Cloudflare (se registra en H6).
