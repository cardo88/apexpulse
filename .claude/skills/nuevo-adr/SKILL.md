---
name: nuevo-adr
description: Registra una decisión de arquitectura o de alcance de ApexPulse como ADR corto en docs/adr/. Usar al elegir entre alternativas con consecuencias que cuestan revertir (tecnología, proveedor, formato de datos, alcance del MVP, licencia) o al cambiar una decisión previa.
---

# Nuevo ADR

1. Tomar el siguiente número libre en docs/adr/ (cuatro dígitos). Revisar en
   docs/adr/README.md los números reservados para decisiones futuras.
2. Copiar docs/adr/template.md a docs/adr/NNNN-titulo-en-kebab.md y
   completarlo. El título se escribe como decisión, no como tema.
3. Agregar la fila en docs/adr/README.md: número, título, estado y fecha.
4. Si reemplaza a otro ADR, marcar el anterior como "Reemplazado por NNNN".
5. Reflejar la decisión en docs/ai/contexto.md, tabla "Decisiones vigentes",
   en una línea con enlace.
6. Cerrar con el skill cambio-documentado.

## Criterios
- Contexto con datos concretos (límites, costos, fechas), no opiniones.
- Al menos una alternativa descartada con su motivo.
- Consecuencias negativas explícitas: qué se pierde o qué hay que vigilar.
- Extensión orientativa: entre 20 y 50 líneas.

## Fuente de verdad
docs/adr/template.md y docs/adr/README.md.
