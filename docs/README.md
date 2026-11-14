# Documentación

Índice de la documentación de ApexPulse. Cada cambio actualiza los documentos afectados en el mismo PR (ver el skill `cambio-documentado`).

| Documento | Contenido | Estado |
|-----------|-----------|--------|
| [roadmap.md](roadmap.md) | Alcance del MVP, hitos, criterios de cierre y estado | Vigente |
| [arquitectura.md](arquitectura.md) | Componentes, flujos y diagramas local y nube | Vigente |
| [fuentes-de-datos.md](fuentes-de-datos.md) | Fuentes, límites, términos, adaptador OpenF1 y validación | Vigente; mapeo a eventos en H1 tarea 5 |
| [adr/](adr/README.md) | Decisiones de arquitectura y alcance | Vigente |
| [ai/contexto.md](ai/contexto.md) | Digest para agentes (200 líneas como máximo) | Vigente |
| [ai/mapa-codigo.md](ai/mapa-codigo.md) | Mapa de módulos generado por `make mapa` | Vigente |
| [setup-local.md](setup-local.md) | Requisitos, comandos make, verificaciones y CI | Vigente; se completa en H1 tarea 8 |
| modelo-de-eventos.md | Esquema de eventos canónicos v1 y versionado | H1 tarea 5 |
| lecturas.md | Catálogo de reglas: condición, umbrales, plantilla, ejemplo | H1 tareas 7 y 8 |
| diseno-visual.md | Tokens, tipografía, componentes y presupuesto de peso | H3 |
| [runbook.md](runbook.md) | Operación ante fallas: fuente caída, esquema roto, nodo caído, baja de contenido | Vigente para fuentes de datos; se completa en H5 |

El plan detallado, la bitácora de trabajo y la operación del nodo propio viven en una capa privada que este repositorio no publica (ADR 0008).

Convenciones:

- Español, lenguaje técnico, sin emoticones, con ejemplos reales y bloques de código.
- Diagramas en Mermaid dentro del Markdown, para que GitHub los renderice.
- Fechas en formato AAAA-MM-DD.
