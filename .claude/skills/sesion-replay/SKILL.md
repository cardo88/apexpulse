---
name: sesion-replay
description: Descarga, normaliza, recorta y reproduce sesiones de F1 en ApexPulse, y regenera las salidas golden. Usar cuando se pida probar con una carrera, preparar un fixture, reproducir una sesión a otra velocidad o actualizar los resultados esperados de los tests.
---

# Sesión y replay

Estado: `make fetch`, `make normalize`, `make replay` y `make fixture` están
disponibles; `make golden` llega en H1 tarea 8. Antes de usarlos, confirmar en la
tabla de comandos de AGENTS.md que existen.

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
| Reproducir sin esperas      | make replay SESSION=2026-monaco-r NOWAIT=1       |
| Recortar un fixture         | make fixture SESSION=2026-monaco-r DESDE=2026-06-07T14:15 HASTA=2026-06-07T15:15 LAPS=57-70 |
| Regenerar golden            | make golden SESSION=2026-sao-paulo-r             |

## Reglas
- Los fixtures se recortan al tramo que prueba algo, pesan menos de 2 MB y se
  versionan en fixtures/sessions/, con un README que diga la consulta original
  y el recorte. Ejemplo: fixtures/sessions/2026-monaco-r/openf1/ (SC con
  paradas, segundo SC y bandera roja, 14:15 a 15:15 UTC).
- Recortar siempre con `make fixture`, nunca a mano: arrastra el último registro
  previo de cada piloto (OpenF1 publica position, intervals y stints solo al
  cambiar). Un recorte a mano deja la consola con `lidera ---`. Los tests de
  contrato del adaptador usan fixtures/contract/ (pocos registros), no sessions/.
- Para una carrera completa sin los endpoints pesados (por ejemplo, para probar paradas):
  `make fixture ... SALIDA=<dir> VACIAR=intervals,position,weather`. Ejemplo:
  fixtures/contract/2026-sao-paulo-r-paradas/.
- `make normalize` es repetible y sin red: después de cambiar el modelo o el
  normalizador, volver a correrlo sobre el crudo de data/raw.
- data/ nunca se versiona.
- Tests del replay: siempre con `FakeClock` (apexpulse.replay.clock), nunca
  con esperas reales. La vuelta es la vuelta en curso del líder (máximo de
  vueltas completadas más uno); ver docs/arquitectura.md#reloj-de-replay.
- Errores de descarga o de esquema: usar el skill fuente-de-datos.
- Golden se regenera solo con un motivo y revisando el diff completo; el
  motivo va en el mensaje del commit.
- El archivo estático de F1 se descarga solo desde la compu o el nodo propio,
  nunca desde CI ni desde la nube.

## Fuente de verdad
docs/setup-local.md (desde H1 tarea 8) y Makefile.
