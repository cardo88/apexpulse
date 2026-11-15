# Respuestas grabadas de OpenF1: 2026-australia-r

Respuestas reales de `https://api.openf1.org/v1` para la carrera de Australia 2026 (Melbourne, session_key 11234), grabadas el 2026-11-15 y recortadas a la ventana de las 04:19:00 a las 04:53:30 UTC (vueltas 12 a 35) sin modificar los registros. Las usa `services/core/tests/test_readings.py`, que las sirve con `httpx.MockTransport`: los tests no usan la red.

Qué cubre el tramo:

- Tres períodos de VSC, con los textos reales de OpenF1 (`VSC DEPLOYED` y `VSC ENDING`, `category=SafetyCar`):
  - Vuelta 12 (04:19:08 a 04:23:07): 10 paradas con detención, todas bajo VSC.
  - Vuelta 18 (04:29:55 a 04:32:26): 3 paradas con detención y 1 cambio de neumáticos sin `stop_duration`.
  - Vuelta 34 (04:52:20 a 04:52:58): 38 s de duración, sin paradas durante el VSC; una pasada a las 04:53:09, con el estado todavía en `VSC_ENDING`.
- Sin Safety Car ni bandera roja.
- Los 22 pilotos de la carrera.

| Archivo | Consulta original | Recorte |
|---------|-------------------|---------|
| sessions.json | `sessions?year=2026` | Solo las 5 sesiones de Melbourne |
| laps.json | `laps?session_key=11234` | Vueltas 12 a 35, la última vuelta completada antes de las 04:19 de cada piloto y la vuelta de inicio de cada stint incluido |
| stints.json | `stints?session_key=11234` | Stints que se superponen con las vueltas 12 a 35 y el último anterior de cada piloto |
| pit.json | `pit?session_key=11234` | `date` entre 04:19:00 y 04:53:30 |
| intervals.json | `intervals?session_key=11234` | Ídem, más el último registro con distancia anterior a las 04:19 y a la largada (04:00, inicio de la sesión) de cada piloto |
| position.json | `position?session_key=11234` | Ídem: más el último registro anterior a las 04:19 y a la largada de cada piloto |
| race_control.json | `race_control?session_key=11234` | `date` entre 04:19:00 y 04:53:30 |
| weather.json | `weather?session_key=11234` | Ídem |
| drivers.json | `drivers?session_key=11234` | Sin recorte (22 pilotos) |

El criterio de arrastre está en el README de [2026-monaco-r](../../2026-monaco-r/openf1/README.md).

Para regrabar, con el crudo ya descargado (`make fetch SESSION=2026-australia-r`):

```bash
make fixture SESSION=2026-australia-r DESDE=2026-03-08T04:19 HASTA=2026-03-08T04:53:30 LAPS=12-35
```

Pesa 1.562.580 bytes (1,49 MiB): `intervals.json` ocupa 1,3 MB. Con tres VSC separados por 34 minutos no hay una ventana más corta; el formato es un registro por línea para que pese menos.
