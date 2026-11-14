# Runbook

Qué hacer ante cada falla conocida: síntoma, causa y corrección. Se completa en H5 con nodo caído, degradación de la web y pedidos de baja de contenido.

## Fuentes de datos

Errores de `make fetch` (adaptador OpenF1). El procedimiento completo ante un cambio de esquema está en el skill `fuente-de-datos`.

| Síntoma | Causa | Corrección |
|---------|-------|------------|
| `AVISO: stints: campos desconocidos: tyre_temperature=98.5` | OpenF1 agregó un campo; la descarga se completa igual | Sumarlo a `known` en `SCHEMAS` de `sources/openf1.py` y a la tabla de [fuentes-de-datos.md](fuentes-de-datos.md#validación-del-esquema) |
| `ERROR: OpenF1 intervals: el registro 0 no tiene gap_to_leader` | Campo obligatorio renombrado o eliminado | Guardar la muestra como fixture, ajustar `SCHEMAS` y el parser; registrar el incidente en esta tabla |
| `ERROR: OpenF1 laps: HTTP 429 tras 6 intentos` | Límite de tasa superado, por ejemplo por otra ejecución que no comparte `data/state/` | Esperar un minuto y reintentar; verificar que todas las ejecuciones usen el mismo `DATA_DIR` |
| `ERROR: OpenF1 laps: HTTP 503 tras 6 intentos` o `error de red` | OpenF1 caído o sin conexión | Reintentar más tarde; lo ya descargado de otras sesiones sigue en caché |
| `ERROR: 2026-las-vegas-r: ... queda disponible desde 2026-11-22T06:30:00+00:00` | La sesión no terminó o terminó hace menos de 30 minutos | Reintentar después de la hora indicada |
| `ERROR: 2026-bahrein-r: la sesión figura como cancelada en OpenF1` | La sesión no se corrió | Ninguna |
| `ERROR: ... no tiene una sesión Race en 'X' para 2026. Circuitos de OpenF1 en 2026: ...` | `circuit_short_name` distinto en ese año, o sesión que no existe (por ejemplo, sprint en un fin de semana sin sprint) | Corregir `openf1` en `services/core/src/apexpulse/config/circuits.toml` con un valor de la lista |
| 403 al descargar desde CI o la nube | Bloqueo de IPs de cloud | Descargar solo desde IP residencial; CI usa fixtures |
| `ERROR: 2026-monaco-r: no hay crudo completo de OpenF1 en ... Correr primero: make fetch SESSION=2026-monaco-r` | `make normalize` sin descarga previa, o descarga interrumpida (sin `manifest.json`) | Correr `make fetch SESSION=<id>` y repetir |
| `ERROR: OpenF1 2026-monaco-r: un registro no cumple el modelo v1: ...` | Un valor fuera de rango o de otro tipo (por ejemplo, un tiempo negativo) que el esquema de descarga no detecta | Guardar el registro como fixture, decidir si se corrige en el normalizador o si cambia el modelo (ver el versionado en [modelo-de-eventos.md](modelo-de-eventos.md#versionado)) |
| `AVISO: laps: vueltas sin tiempo ni vuelta siguiente, omitidas: 7 (por ejemplo piloto 16 vuelta 65)` | Abandonos o la vuelta de la bandera roja: OpenF1 no tiene el tiempo y no hay vuelta siguiente | Ninguna; es esperable en carreras con abandonos |
