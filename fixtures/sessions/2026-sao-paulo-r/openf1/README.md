# Respuestas grabadas de OpenF1: 2026-sao-paulo-r

Respuestas reales de `https://api.openf1.org/v1` para la carrera de São Paulo 2026 (session_key 11412), grabadas el 2026-11-14 y recortadas a la ventana de las 17:19 a las 17:33 UTC (vueltas 12 a 20) sin modificar los registros. Las usa `services/core/tests/test_replay.py`, que las sirve con `httpx.MockTransport`: los tests no usan la red.

Qué cubre el tramo:

- La primera tanda de paradas bajo bandera verde: 21 pasadas por boxes en las vueltas 14 a 17 (`lap_number` de `pit`).
- 3 pasadas sin `stop_duration` (HAD vuelta 16, VER y ALO vuelta 17) con 23,7 a 24,1 s en el pit lane, dentro del rango de las paradas con detención normales (23,7 a 25,6 s). Todas abren un stint nuevo en la vuelta siguiente (stint 2, SOFT). Sirven para probar la definición de parada real.
- Sin Safety Car ni VSC: la carrera de São Paulo no tuvo neutralizaciones.
- Los 22 pilotos de la carrera.

| Archivo | Consulta original | Recorte |
|---------|-------------------|---------|
| sessions.json | `sessions?year=2026` | Solo las 5 sesiones de Interlagos |
| laps.json | `laps?session_key=11412` | Vueltas 12 a 20, la última vuelta completada antes de las 17:19 de cada piloto y la vuelta de inicio de cada stint incluido |
| stints.json | `stints?session_key=11412` | Stints que se superponen con las vueltas 12 a 20 y el último anterior de cada piloto |
| pit.json | `pit?session_key=11412` | `date` entre 17:19:00 y 17:33:00 |
| intervals.json | `intervals?session_key=11412` | Ídem, más el último registro con distancia anterior a las 17:19 y a la largada (17:00) de cada piloto |
| position.json | `position?session_key=11412` | Ídem: más el último registro anterior a las 17:19 y a la largada de cada piloto |
| race_control.json | `race_control?session_key=11412` | `date` entre 17:19:00 y 17:33:00 |
| weather.json | `weather?session_key=11412` | Ídem |
| drivers.json | `drivers?session_key=11412` | Sin recorte (22 pilotos) |

El criterio de arrastre y sus consecuencias están explicados en el README de [2026-monaco-r](../../2026-monaco-r/openf1/README.md). El líder de la primera línea de la consola es NOR, el P1 de la grilla; al llegar a las 17:19 es ANT.

Para regrabar, con el crudo ya descargado (`make fetch SESSION=2026-sao-paulo-r`):

```bash
make fixture SESSION=2026-sao-paulo-r DESDE=2026-11-08T17:19 HASTA=2026-11-08T17:33 LAPS=12-20
```

Pesa 0,9 MB.
