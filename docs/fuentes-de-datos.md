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

`make fetch SESSION=2026-sao-paulo-r` baja la sesión en 9 requests y la deja en caché:

```text
2026-sao-paulo-r (openf1, session_key 11412): 9 requests
  laps             1437 registros
  stints             80 registros
  pit                58 registros
  intervals       29368 registros
  position          576 registros
  race_control      212 registros
  weather           160 registros
  drivers            22 registros
Crudo en .../data/raw/2026/2026-sao-paulo-r/openf1
```

1. Si existe `data/raw/<año>/<sesion>/openf1/manifest.json` con todos los endpoints y sus archivos, no hace ningún request. Si faltan endpoints, por ejemplo en un crudo bajado antes de sumar `drivers`, pide solo esos, reutiliza el registro de la sesión del manifiesto y lo reescribe: `make fetch SESSION=2026-monaco-r` sobre la caché anterior a `drivers` hizo `1 requests`. `FORCE=1` ignora la caché y baja todo.
2. Resuelve el `session_key` con `sessions?year=<año>`, filtrando por `circuit_short_name` (columna `openf1` de `services/core/src/apexpulse/config/circuits.toml`) y `session_name`. La lista del año se cachea en `data/raw/<año>/_openf1/sessions.jsonl.zst`; si la sesión no está en caché, se vuelve a pedir (el calendario del año en curso se completa con el tiempo).
3. Rechaza la sesión si `is_cancelled` es verdadero o si todavía no pasaron 30 minutos desde `date_end`.
4. Pide cada endpoint con `?session_key=<n>`, valida el esquema y guarda el crudo tal como llegó en `<endpoint>.jsonl.zst`. Un 404 con `No results found` cuenta como lista vacía y genera un aviso.
5. Escribe `manifest.json` al final, con el registro de la sesión, los conteos y los avisos. Sin manifiesto, la descarga se considera incompleta y se rehace entera.

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
| drivers | session_key, driver_number, name_acronym | meeting_key, full_name, first_name, last_name, broadcast_name, team_name, team_colour, headshot_url, country_code |

Un campo obligatorio puede venir en `null` (por ejemplo, `lap_duration` de la vuelta 1); lo que falla es que la clave no exista.

### Tests

`services/core/tests/contract/test_openf1.py` usa las respuestas mínimas de `fixtures/contract/2026-sao-paulo-r/openf1/` (tres registros por endpoint) servidas con `httpx.MockTransport`. `test_openf1_normalize.py`, `test_replay.py` y `test_readings.py` usan los recortes de `fixtures/sessions/2026-monaco-r/openf1/` (tramo del SC, las paradas bajo SC y la bandera roja), `fixtures/sessions/2026-sao-paulo-r/openf1/` (primera tanda de paradas, vueltas 12 a 20) y `fixtures/sessions/2026-australia-r/openf1/` (tres VSC, vueltas 12 a 35); `test_golden.py`, `test_propiedades.py` y `test_pipeline.py` corren el camino completo sobre los tres recortes de `sessions/`; `test_readings.py` usa además `fixtures/contract/2026-sao-paulo-r-paradas/openf1/` (carrera completa solo con `pit`, `stints`, `laps` y `race_control`): descargan los endpoints contra OpenF1 simulado y verifican la normalización. `tests/conftest.py` bloquea los sockets: un test que intente usar la red falla. Diagnóstico de errores en [runbook.md](runbook.md#fuentes-de-datos).

### Recorte de fixtures

`make fixture SESSION=<id> DESDE=<iso> HASTA=<iso> LAPS=<a>-<b>` parte del crudo de `data/raw` y escribe los JSON en `fixtures/sessions/<id>/openf1/` sin modificar ningún registro. OpenF1 publica `position`, `intervals` y los stints solo cuando el valor cambia, así que un recorte por tiempo pierde el estado de arranque. Criterio:

| Endpoint | Qué conserva |
|----------|--------------|
| `pit`, `race_control`, `weather` | `date` dentro de la ventana |
| `position` | Ventana, más el último registro anterior a ella y el último anterior a la largada, de cada piloto |
| `intervals` | Ídem, solo registros con alguna distancia (el normalizador descarta los demás) |
| `stints` | Los que se superponen con el rango de vueltas y el último anterior de cada piloto |
| `laps` | Rango de vueltas, la última completada antes de la ventana de cada piloto y la vuelta de inicio de cada stint incluido (el normalizador fecha un stint con esa fila) |
| `drivers` | Todos |
| `sessions` | Las del mismo fin de semana (`meeting_key`) |

Los archivos tienen un registro por línea, sin modificarlo. `--vaciar` escribe como lista vacía los endpoints que se indiquen.

Los registros arrastrados conservan su fecha: el replay pliega sin emitir los anteriores a la largada y emite el resto durante el hueco previo a la ventana, donde el contador de vuelta no es confiable. Al llegar a la ventana el estado coincide con el de la sesión completa (posición, intervalo y stint de cada piloto, líder y vuelta).

### Textos de dirección de carrera

OpenF1 publica el VSC como `VSC DEPLOYED` y `VSC ENDING` con `category=SafetyCar`, no con la forma larga de la FIA. `sources/trackstatus.py` acepta las dos. Detalle en [modelo-de-eventos.md](modelo-de-eventos.md#estado-de-pista).

### Paradas y stints

El campo `stop_duration` de `pit` puede faltar en paradas reales (5 de 58 en São Paulo, 54 de 86 en Mónaco, la mayoría pasadas por el pit lane bajo SC y bandera roja). `lap_start` del stint nuevo coincide con `lap_number` de la pasada en Mónaco y es la vuelta siguiente en São Paulo, y bajo SC OpenF1 abre un stint por cada pasada aunque el juego de neumáticos no cambie. Una regla que necesite saber si hubo cambio de neumáticos no puede usar solo `stop_duration` ni solo el número de stint.

`lap_number` de `pit` tampoco es siempre confiable: en Australia 10 de 26 pasadas traen una vuelta que no es la del piloto en ese instante (46 para las cinco paradas bajo el VSC de la vuelta 12; en Mónaco y São Paulo, 0 de 86 y 0 de 58). Desde H2 el normalizador no usa ese campo: deriva `PitLane.lap` de `laps`, por el instante de la pasada (`date` llega muy cerca del cruce de línea que abre la vuelta siguiente a la de la pasada, así que se usa la vuelta anterior a la última ya iniciada en ese instante). Sin una vuelta anterior conocida del piloto, se usa el crudo con un aviso (`pit: vuelta no derivable desde laps, se usa lap_number crudo`). Detalle y verificación contra el stint nuevo de cada pasada en [lecturas.md](lecturas.md#parada-real).

Lo que el normalizador omite se informa como aviso (`AVISO:` en `make normalize`). Medido sobre las carreras completas: stints sin `tyre_age_at_start`, 0 en Mónaco, São Paulo y Australia (aviso cubierto por un test de contrato); stints cuya vuelta de inicio no está en `laps`, 1 en Australia (piloto 27, stint 1: su única vuelta registrada, la 1, llega con `date_start` nulo; no hay otro dato de esa vuelta en `laps` para ubicar el stint, así que se omite); vueltas sin tiempo ni vuelta siguiente, 7 en Mónaco, 2 en São Paulo y 3 en Australia, más 2 sin `date_start` en Australia (una de ellas, la del piloto 27).

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
| pit | `pit` | `t` = `date`; `lap` derivado de `laps` por el instante (no `lap_number`, ver abajo); `lane_s` = `lane_duration` (o `pit_duration` si falta); `stationary_s` = `stop_duration` |
| position | `position` | `t` = `date`; `position` |
| intervals | `interval` | `t` = `date`; número en `gap_to_leader` a `gap_s`, `"+N LAP"` o `"+N LAPS"` a `laps_down`; lo mismo para `interval`. Registros con ambos null se omiten |
| race_control | `race_control` | `t` = `date`; `category`, `message`, `flag`, `scope`, `sector`; `driver` = `driver_number`; `lap` = `lap_number` |
| race_control | `track_status` | Derivado con `sources/trackstatus.py`; ver [Estado de pista](modelo-de-eventos.md#estado-de-pista) |
| weather | `weather` | `t` = `date`; `air_c`, `track_c` = `air_temperature`, `track_temperature`; `rain` = `rainfall` > 0; `humidity_pct`, `wind_ms`, `wind_deg`, `pressure_hpa` = `humidity`, `wind_speed`, `wind_direction`, `pressure` |
| drivers | `driver` | `t` = `date_start` de la sesión (el endpoint no trae fecha); `acronym` = `name_acronym`; `name` = `first_name` + `last_name` (`"Lewis Hamilton"`), o `full_name` si falta alguno; `team` = `team_name`. Sin `name_acronym` de 3 letras o sin nombre: se omite con aviso. Número repetido con datos distintos: queda el último, con aviso. `team_colour`, `headshot_url`, `broadcast_name` y `country_code` no se usan |
| sessions | Cabecera `SessionMeta` | `source_session_key` = `session_key`; `start`, `end` = `date_start`, `date_end` (calendario, no hora real) |

Particularidades de OpenF1 verificadas con 2026-monaco-r (session_key 11299):

- Con `ALL CARS THROUGH THE PIT LANE` bajo SC, cada auto genera un registro en `pit` sin `stop_duration` (en Mónaco, 18 pasadas y 5 paradas reales durante el SC de la vuelta 60). Solo `stop_duration` distingue una parada de una pasada.
- Esas pasadas también abren un stint nuevo con el mismo compuesto y `tyre_age_at_start` corrido en una vuelta (por ejemplo, ALO: stint 3 SOFT con 0 vueltas desde la 58 y stint 4 SOFT con 1 desde la 59). Un juego nuevo se reconoce por `tyre_age` 0 o por el cambio de compuesto.
- La bandera roja llega como `category=Other`, `message="RED FLAG - RACE SUSPENDED"`, sin `flag=RED`, junto con `SessionStatus SESSION ABORTED`.
- Durante la bandera roja, los autos esperan en el pit lane: `lane_duration` supera los 2000 s.
- `drivers` devuelve un registro por auto inscripto (22 en 2026), sin fecha. `full_name` trae el apellido en mayúsculas (`"Lewis HAMILTON"`); por eso el nombre se arma con `first_name` y `last_name`. La grilla cambia entre carreras: en Mónaco corre OCO (31) y en São Paulo, CAM (51).

## Referencias

- FastF1 v3.7.0, nuevo endpoint y autenticación: https://newreleases.io/project/github/theOehrly/Fast-F1/release/v3.7.0
- Tópicos que requieren F1 TV: https://nicxe.github.io/f1_sensor/help/experimental-testing
- 403 desde entornos cloud: https://github.com/theOehrly/Fast-F1/discussions/949
- OpenF1, tiers y límites: https://freeapihub.com/apis/openf1-api
- Jolpica-F1, límites: https://docs.rs/crate/f1_data/latest/source/src/jolpica/api.rs
