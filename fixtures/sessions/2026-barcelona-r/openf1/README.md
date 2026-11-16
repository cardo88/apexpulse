# Respuestas grabadas de OpenF1: 2026-barcelona-r

Respuestas reales de `https://api.openf1.org/v1` para la carrera de España 2026 en Catalunya (session_key 11307), grabadas el 2026-11-15 y recortadas a la ventana de las 13:07:35 a las 13:24:08 UTC (vueltas 4 a 14) sin modificar los registros. Carrera seca, sin Safety Car ni VSC en esta ventana (el único VSC de la carrera es en las vueltas 63 a 65, fuera del recorte). La usa la calibración de `undercut_window` (H2 t2).

Qué cubre el tramo:

- La primera tanda de paradas en verde: 14 pasadas por boxes en las vueltas 9 a 13.
- De esos pilotos, 9 pares perseguidor-rival abren una ventana de undercut con los umbrales de hoy (`max_gap_s=2,0`, `min_tyre_age_laps=10`): verificado con `make replay SESSION=2026-barcelona-r NOWAIT=1`. El resto de las paradas de la tanda no abre ventana (gap o edad fuera de umbral, o sin rival comparable): sirve para probar los dos casos, con y sin lectura.
- Sin `cheap_stop`: ninguna pasada ocurre bajo neutralización.
- Los 22 pilotos de la carrera.

| Archivo | Consulta original | Recorte |
|---------|-------------------|---------|
| sessions.json | `sessions?year=2026` | Solo las sesiones de Catalunya |
| laps.json | `laps?session_key=11307` | Vueltas 4 a 14, la última vuelta completada antes de la ventana de cada piloto y la vuelta de inicio de cada stint incluido |
| stints.json | `stints?session_key=11307` | Stints que se superponen con las vueltas 4 a 14 y el último anterior de cada piloto |
| pit.json | `pit?session_key=11307` | `date` entre 13:07:35 y 13:24:08 |
| intervals.json | `intervals?session_key=11307` | Ídem, más el último registro con distancia anterior a la ventana y a la largada de cada piloto |
| position.json | `position?session_key=11307` | Ídem: más el último registro anterior a la ventana y a la largada de cada piloto |
| race_control.json | `race_control?session_key=11307` | `date` entre 13:07:35 y 13:24:08 |
| weather.json | `weather?session_key=11307` | Ídem |
| drivers.json | `drivers?session_key=11307` | Sin recorte (22 pilotos) |

El criterio de arrastre y sus consecuencias están explicados en el README de [2026-monaco-r](../../2026-monaco-r/openf1/README.md). La ventana se eligió terminando justo después de la última lectura de la tanda (vuelta 13), con margen hasta que el piloto más lento del rango completa la vuelta 14: extenderla hasta la 17 u 18 agrega una pareja (ALO/OCO) cuyo `interval_s` en el recorte no coincide con el de la carrera completa; es un límite del recorte por fecha cerca de `HASTA`, no un error de la regla, explicado en [fuentes-de-datos.md](../../../../docs/fuentes-de-datos.md#recorte-de-fixtures).

Para regrabar, con el crudo ya descargado (`make fetch SESSION=2026-barcelona-r`):

```bash
make fixture SESSION=2026-barcelona-r DESDE=2026-06-14T13:07:35 HASTA=2026-06-14T13:24:08 LAPS=4-14
```

Pesa 0,9 MB.
