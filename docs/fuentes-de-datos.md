# Fuentes de datos

Todas las fuentes son públicas y no oficiales. El esquema del feed de F1 se obtuvo por ingeniería inversa y cambió durante 2025 y 2026; por eso cada fuente tiene un adaptador aislado y el crudo se guarda siempre. Última verificación: 2026-11-14.

## Resumen

| Fuente | Uso en el proyecto | Acceso | Límites | Restricción clave |
|--------|--------------------|--------|---------|-------------------|
| OpenF1 | Fuente primaria del MVP (histórico) | Histórico desde 2023 sin autenticación; vivo con tier Sponsor (EUR 9,90 por mes) | 3 req/s y 30 req/min | Caché local obligatoria; uso personal y no comercial |
| Archivo estático de F1 Live Timing | Segunda fuente; mismo formato que el vivo | Sin autenticación | No publicados | Bloqueos desde IPs de cloud: descargar solo desde IP residencial; no redistribuir el crudo |
| F1 Live Timing (SignalR) | Vivo en H7 | Endpoint `/signalrcore`; sin autenticación solo llegan los tópicos públicos | No publicados | Sin credenciales de F1 TV; bloqueo de IPs de cloud |
| Jolpica-F1 | Contexto: resultados y standings | Sin autenticación | 4 req/s en ráfaga y 500 req/h | Planean tokens y bajar el límite sin autenticación |
| FastF1 | Validación y herramientas; no forma parte del núcleo | Librería Python (MIT) | Hereda los del archivo estático | Dependencia pesada |

## OpenF1

- URL base: `https://api.openf1.org/v1`.
- Endpoints que usa el MVP: `sessions`, `laps`, `stints`, `pit`, `intervals`, `position`, `race_control`, `weather`.
- El vivo pago cubre desde 30 minutos antes hasta 30 minutos después de cada sesión; pasado ese plazo, los datos quedan libres como histórico.
- Ejemplo de consulta:

```bash
curl -s "https://api.openf1.org/v1/sessions?year=2026&session_name=Race" | head -c 400
```

### Adaptador (`sources/openf1.py`)

`make fetch SESSION=2026-sao-paulo-r` baja la sesión en 8 requests y la deja en caché:

```text
2026-sao-paulo-r (openf1, session_key 11412): 8 requests
  laps             1437 registros
  stints             80 registros
  pit                58 registros
  intervals       29368 registros
  position          576 registros
  race_control      212 registros
  weather           160 registros
Crudo en .../data/raw/2026/2026-sao-paulo-r/openf1
```

1. Si existe `data/raw/<año>/<sesion>/openf1/manifest.json`, no hace ningún request. `FORCE=1` ignora la caché.
2. Resuelve el `session_key` con `sessions?year=<año>`, filtrando por `circuit_short_name` (columna `openf1` de `services/core/src/apexpulse/config/circuits.toml`) y `session_name`. La lista del año se cachea en `data/raw/<año>/_openf1/sessions.jsonl.zst`; si la sesión no está en caché, se vuelve a pedir (el calendario del año en curso se completa con el tiempo).
3. Rechaza la sesión si `is_cancelled` es verdadero o si todavía no pasaron 30 minutos desde `date_end`.
4. Pide cada endpoint con `?session_key=<n>`, valida el esquema y guarda el crudo tal como llegó en `<endpoint>.jsonl.zst`. Un 404 con `No results found` cuenta como lista vacía y genera un aviso.
5. Escribe `manifest.json` al final, con el registro de la sesión, los conteos y los avisos. Sin manifiesto, la descarga se considera incompleta y se rehace.

Tipos de sesión del identificador y su `session_name` en OpenF1:

| Tipo | session_name |
|------|--------------|
| r | Race |
| q | Qualifying |
| s | Sprint |
| sq | Sprint Qualifying (Sprint Shootout en 2023) |
| fp1, fp2, fp3 | Practice 1, Practice 2, Practice 3 |

Los ensayos de pretemporada (`Day 1` a `Day 3`) no tienen tipo en el identificador.

### Límite de tasa y reintentos

- `RateLimiter` con dos ventanas deslizantes: 3 requests en cualquier segundo y 30 en cualquier minuto.
- Los instantes de los últimos requests se guardan en `data/state/openf1-ratelimit.json`: varias ejecuciones de `make fetch` seguidas comparten el presupuesto.
- Ante 429, 5xx o error de red reintenta hasta 5 veces. Espera lo que indique `Retry-After`, o 1, 2, 4, 8 y 16 s (máximo 60 s).

### Validación del esquema

Verificada contra `2026-sao-paulo-r` (session_key 11412) y `2026-monaco-r` (session_key 11299) el 2026-11-14. Un campo obligatorio faltante, o un registro de otra sesión, hace fallar la descarga con `SchemaError`. Un campo que no figura en la lista de conocidos genera un aviso con una muestra, por ejemplo `stints: campos desconocidos: tyre_temperature=98.5`.

| Endpoint | Obligatorios | Otros conocidos |
|----------|--------------|-----------------|
| sessions | session_key, meeting_key, year, session_name, circuit_short_name, date_start, date_end | session_type, circuit_key, country_key, country_code, country_name, location, gmt_offset, is_cancelled |
| laps | session_key, driver_number, lap_number, date_start, lap_duration | meeting_key, duration_sector_1 a 3, i1_speed, i2_speed, st_speed, is_pit_out_lap, segments_sector_1 a 3 |
| stints | session_key, driver_number, stint_number, lap_start, lap_end, compound | meeting_key, tyre_age_at_start |
| pit | session_key, driver_number, lap_number, date | meeting_key, pit_duration, stop_duration, lane_duration |
| intervals | session_key, driver_number, date, gap_to_leader, interval | meeting_key |
| position | session_key, driver_number, date, position | meeting_key |
| race_control | session_key, date, category, message | meeting_key, driver_number, lap_number, flag, scope, sector, qualifying_phase |
| weather | session_key, date, air_temperature, track_temperature, rainfall | meeting_key, humidity, pressure, wind_direction, wind_speed |

Un campo obligatorio puede venir en `null` (por ejemplo, `lap_duration` de la vuelta 1); lo que falla es que la clave no exista.

### Tests

`services/core/tests/contract/test_openf1.py` usa las respuestas grabadas de `fixtures/sessions/2026-sao-paulo-r/openf1/` servidas con `httpx.MockTransport`. `test_openf1_normalize.py` usa `fixtures/sessions/2026-monaco-r/openf1/` (tramo del SC, las paradas bajo SC y la bandera roja): descarga `race_control` y el resto de los endpoints contra OpenF1 simulado y verifica la normalización. `tests/conftest.py` bloquea los sockets: un test que intente usar la red falla. Diagnóstico de errores en [runbook.md](runbook.md#fuentes-de-datos).

## Archivo estático de F1 Live Timing

- Estructura: `https://livetiming.formula1.com/static/<año>/<fecha>_<evento>/<fecha>_<sesion>/<Topico>.jsonStream`.
- Tópicos que usa el proyecto: `TimingData`, `TimingAppData`, `RaceControlMessages`, `TrackStatus`, `WeatherData`, `LapCount`, `SessionInfo`, `DriverList`.
- Desde entornos cloud se reportaron respuestas 403. CI usa fixtures versionados; nunca descarga de esta fuente.

## F1 Live Timing en vivo (H7)

- Migró del SignalR clásico a ASP.NET Core SignalR.
- Requieren F1 TV, y por lo tanto quedan fuera del proyecto: `CarData.z`, `TeamRadio`, `PitStopSeries`, `DriverRaceInfo`, `ChampionshipPrediction`.
- Pendiente: confirmar con una grabación real qué tópicos llegan sin autenticación en 2026.

## Jolpica-F1

- URL base: `https://api.jolpi.ca/ergast/f1`, compatible con Ergast.
- Uso: standings y resultados para dar contexto al post-carrera.

## Reglas de uso

- El crudo se guarda comprimido antes de normalizar.
- Respetar límites con backoff exponencial ante 429.
- Ninguna descarga desde la nube o desde CI contra F1.
- Solo se publican datos derivados.

## Mapeo a eventos canónicos

`make normalize SESSION=<id>` lee el crudo de OpenF1 y escribe los eventos canónicos v1 en `data/canonical/<sesion>.parquet` (`sources/openf1_normalize.py`). Esquema y versionado en [modelo-de-eventos.md](modelo-de-eventos.md).

| Endpoint | Evento | Mapeo |
|----------|--------|-------|
| laps | `lap` | `t` = `date_start` + `lap_duration`; si `lap_duration` es null, el `date_start` de la vuelta siguiente del piloto. `lap_time_s` = `lap_duration`; `s1_s` a `s3_s` = `duration_sector_1` a `3`; `pit_out` = `is_pit_out_lap`. Sin `date_start`, o sin tiempo ni vuelta siguiente: se omite con aviso |
| stints | `stint` | `t` = `date_start` de la vuelta `lap_start` del piloto; `stint` = `stint_number`; `compound` en mayúsculas (desconocido: `UNKNOWN` con aviso); `tyre_age` = `tyre_age_at_start`. `lap_end` no se usa: sería información del futuro |
| pit | `pit` | `t` = `date`; `lane_s` = `lane_duration` (o `pit_duration` si falta); `stationary_s` = `stop_duration` |
| position | `position` | `t` = `date`; `position` |
| intervals | `interval` | `t` = `date`; número en `gap_to_leader` a `gap_s`, `"+N LAP"` o `"+N LAPS"` a `laps_down`; lo mismo para `interval`. Registros con ambos null se omiten |
| race_control | `race_control` | `t` = `date`; `category`, `message`, `flag`, `scope`, `sector`; `driver` = `driver_number`; `lap` = `lap_number` |
| race_control | `track_status` | Derivado con `sources/trackstatus.py`; ver [Estado de pista](modelo-de-eventos.md#estado-de-pista) |
| weather | `weather` | `t` = `date`; `air_c`, `track_c` = `air_temperature`, `track_temperature`; `rain` = `rainfall` > 0; `humidity_pct`, `wind_ms`, `wind_deg`, `pressure_hpa` = `humidity`, `wind_speed`, `wind_direction`, `pressure` |
| sessions | Cabecera `SessionMeta` | `source_session_key` = `session_key`; `start`, `end` = `date_start`, `date_end` (calendario, no hora real) |

Particularidades de OpenF1 verificadas con 2026-monaco-r (session_key 11299):

- Con `ALL CARS THROUGH THE PIT LANE` bajo SC, cada auto genera un registro en `pit` sin `stop_duration` (en Mónaco, 18 pasadas y 5 paradas reales durante el SC de la vuelta 60). Solo `stop_duration` distingue una parada de una pasada.
- Esas pasadas también abren un stint nuevo con el mismo compuesto y `tyre_age_at_start` corrido en una vuelta (por ejemplo, ALO: stint 3 SOFT con 0 vueltas desde la 58 y stint 4 SOFT con 1 desde la 59). Un juego nuevo se reconoce por `tyre_age` 0 o por el cambio de compuesto.
- La bandera roja llega como `category=Other`, `message="RED FLAG - RACE SUSPENDED"`, sin `flag=RED`, junto con `SessionStatus SESSION ABORTED`.
- Durante la bandera roja, los autos esperan en el pit lane: `lane_duration` supera los 2000 s.

## Referencias

- FastF1 v3.7.0, nuevo endpoint y autenticación: https://newreleases.io/project/github/theOehrly/Fast-F1/release/v3.7.0
- Tópicos que requieren F1 TV: https://nicxe.github.io/f1_sensor/help/experimental-testing
- 403 desde entornos cloud: https://github.com/theOehrly/Fast-F1/discussions/949
- OpenF1, tiers y límites: https://freeapihub.com/apis/openf1-api
- Jolpica-F1, límites: https://docs.rs/crate/f1_data/latest/source/src/jolpica/api.rs
