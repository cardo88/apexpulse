# Respuestas grabadas de OpenF1: 2026-sao-paulo-r, carrera completa sin intervalos

Respuestas reales de `https://api.openf1.org/v1` para la carrera de São Paulo 2026 (session_key 11412), grabadas el 2026-11-14. Cubren toda la carrera pero solo con los endpoints que necesita el seguimiento de paradas: `laps`, `stints`, `pit`, `race_control` y `drivers`. `position`, `intervals` y `weather` están vacíos (`[]`). Las usa `services/core/tests/test_readings.py`, que las sirve con `httpx.MockTransport`: los tests no usan la red.

Para qué sirve: las 5 pasadas sin `stop_duration` de São Paulo (HAD vuelta 16, VER y ALO vuelta 17, COL vuelta 53 y HAD vuelta 62) están repartidas en toda la carrera, y la ventana de `fixtures/sessions/2026-sao-paulo-r/` solo cubre las 3 primeras. Con este fixture un test verifica que las 5 son paradas reales por stint y que hay 58 paradas reales en 58 pasadas.

| Archivo | Consulta original | Recorte |
|---------|-------------------|---------|
| sessions.json | `sessions?year=2026` | Solo las 5 sesiones de Interlagos |
| laps.json | `laps?session_key=11412` | Sin recorte (1437 registros) |
| stints.json | `stints?session_key=11412` | Sin recorte (80 registros) |
| pit.json | `pit?session_key=11412` | Sin recorte (58 registros) |
| race_control.json | `race_control?session_key=11412` | Sin recorte (212 registros) |
| drivers.json | `drivers?session_key=11412` | Sin recorte (22 pilotos) |
| position.json, intervals.json, weather.json | | Vacíos |

Para regrabar, con el crudo ya descargado:

```bash
make fixture SESSION=2026-sao-paulo-r DESDE=2026-11-08T16:00 HASTA=2026-11-08T19:00 LAPS=1-80 \
  SALIDA=$PWD/fixtures/contract/2026-sao-paulo-r-paradas/openf1 VACIAR=intervals,position,weather
```

Pesa 0,75 MB.
