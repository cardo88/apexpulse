# Fuentes de datos

Todas las fuentes son públicas y no oficiales. El esquema del feed de F1 se obtuvo por ingeniería inversa y cambió durante 2025 y 2026; por eso cada fuente tiene un adaptador aislado y el crudo se guarda siempre. Última verificación: 2026-11-08.

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

Se completa en H1, tarea 5, junto con docs/modelo-de-eventos.md.

## Referencias

- FastF1 v3.7.0, nuevo endpoint y autenticación: https://newreleases.io/project/github/theOehrly/Fast-F1/release/v3.7.0
- Tópicos que requieren F1 TV: https://nicxe.github.io/f1_sensor/help/experimental-testing
- 403 desde entornos cloud: https://github.com/theOehrly/Fast-F1/discussions/949
- OpenF1, tiers y límites: https://freeapihub.com/apis/openf1-api
- Jolpica-F1, límites: https://docs.rs/crate/f1_data/latest/source/src/jolpica/api.rs
