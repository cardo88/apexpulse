# Respuestas grabadas de OpenF1: 2026-monaco-r

Respuestas reales de `https://api.openf1.org/v1` para la carrera de Mónaco 2026 (session_key 11299), grabadas el 2026-11-14 y recortadas al tramo entre las 14:15 y las 15:15 UTC sin modificar los registros. Las usa `services/core/tests/contract/test_openf1_normalize.py`, que las sirve con `httpx.MockTransport`: los tests no usan la red.

Qué cubre el tramo:

- SC desde la vuelta 60 (14:20:02) hasta el TRACK CLEAR de las 14:30:34, con 5 paradas reales (HAM, ALO, RUS, PER, BOR, entre 2,5 y 8,6 s detenidos) y 18 pasadas por el pit lane sin detención (`ALL CARS THROUGH THE PIT LANE`).
- Segundo SC en la vuelta 66 (14:31:18).
- Bandera roja en la vuelta 68 (14:35:06), un TRACK CLEAR con la carrera suspendida (15:00:48) y la reanudación (15:12:00).
- Autos doblados (`gap_to_leader` igual a `"+1 LAP"`).

| Archivo | Consulta original | Recorte |
|---------|-------------------|---------|
| sessions.json | `sessions?year=2026` | Solo las 5 sesiones de Monte Carlo |
| laps.json | `laps?session_key=11299` | Vueltas 57 a 70 |
| stints.json | `stints?session_key=11299` | Stints que se superponen con las vueltas 57 a 70 |
| pit.json | `pit?session_key=11299` | `date` entre 14:15:00 y 15:15:00 |
| intervals.json | `intervals?session_key=11299` | Ídem |
| position.json | `position?session_key=11299` | Ídem |
| race_control.json | `race_control?session_key=11299` | Ídem |
| weather.json | `weather?session_key=11299` | Ídem |

Para regrabar: `make fetch SESSION=2026-monaco-r FORCE=1` y recortar desde `data/raw/2026/2026-monaco-r/openf1/` con el mismo criterio. Pesa 1,1 MB; intervals.json ocupa la mayor parte.
