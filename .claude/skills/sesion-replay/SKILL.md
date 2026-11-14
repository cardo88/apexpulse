---
name: sesion-replay
description: Descarga, normaliza, recorta y reproduce sesiones de F1 en ApexPulse, y regenera las salidas golden. Usar cuando se pida probar con una carrera, preparar un fixture, reproducir una sesión a otra velocidad o actualizar los resultados esperados de los tests.
---

# Sesión y replay

Estado: `make fetch` está disponible; el resto de los targets llega en H1,
tareas 5 a 8. Antes de usarlos, confirmar en la tabla de comandos de AGENTS.md
que existen.

## Identificador de sesión
`<año>-<circuito>-<tipo>`, con tipo r, q, s, sq, fp1, fp2 o fp3.
Ejemplo: 2026-sao-paulo-r. La tabla de circuitos vive en
services/core/src/apexpulse/config/circuits.toml.

## Comandos
| Objetivo                    | Comando                                          |
|-----------------------------|--------------------------------------------------|
| Descargar y cachear         | make fetch SESSION=2026-sao-paulo-r              |
| Volver a descargar          | make fetch SESSION=2026-sao-paulo-r FORCE=1      |
| Normalizar                  | make normalize SESSION=2026-sao-paulo-r          |
| Reproducir por consola      | make replay SESSION=2026-sao-paulo-r SPEED=30    |
| Reproducir desde una vuelta | make replay SESSION=2026-sao-paulo-r FROM_LAP=40 |
| Recortar un fixture         | make fixture SESSION=2026-sao-paulo-r LAPS=30-45 |
| Regenerar golden            | make golden SESSION=2026-sao-paulo-r             |

## Reglas
- Los fixtures se recortan al tramo que prueba algo, pesan menos de 2 MB y se
  versionan en fixtures/sessions/.
- data/ nunca se versiona.
- Errores de descarga o de esquema: usar el skill fuente-de-datos.
- Golden se regenera solo con un motivo y revisando el diff completo; el
  motivo va en el mensaje del commit.
- El archivo estático de F1 se descarga solo desde la compu o el nodo propio,
  nunca desde CI ni desde la nube.

## Fuente de verdad
docs/setup-local.md (desde H1 tarea 8) y Makefile.
