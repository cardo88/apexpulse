# Respuestas grabadas de OpenF1: 2026-sao-paulo-r

Respuestas reales de `https://api.openf1.org/v1`, grabadas el 2026-11-14 y recortadas a pocos registros sin modificarlos. Las usa `services/core/tests/contract/test_openf1.py`, que las sirve con `httpx.MockTransport`: los tests no usan la red.

| Archivo | Consulta original | Recorte |
|---------|-------------------|---------|
| sessions.json | `sessions?year=2026` | Solo los circuitos Interlagos y Sakhir (16 sesiones); la carrera de Sakhir figura cancelada |
| laps.json | `laps?session_key=11412` | Vuelta 1 de dos pilotos y vuelta 10 de dos pilotos |
| stints.json | `stints?session_key=11412` | Primeros 3 |
| pit.json | `pit?session_key=11412` | Primeros 3 |
| intervals.json | `intervals?session_key=11412` | Primeros 3 |
| position.json | `position?session_key=11412` | Primeros 3 |
| race_control.json | `race_control?session_key=11412` | 2 sin bandera y 2 con bandera |
| weather.json | `weather?session_key=11412` | Primeros 3 |

Para regrabar: `make fetch SESSION=2026-sao-paulo-r FORCE=1` y recortar desde `data/raw/2026/2026-sao-paulo-r/openf1/` con el mismo criterio. Si cambia el esquema, el test de contrato lo detecta.
