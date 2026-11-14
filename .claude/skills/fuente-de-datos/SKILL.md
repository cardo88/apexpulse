---
name: fuente-de-datos
description: Agrega o modifica un adaptador de fuente de datos de ApexPulse (OpenF1, archivo estático de F1 Live Timing, Jolpica-F1, feed en vivo) o diagnostica y corrige un cambio de esquema o de endpoint. Usar ante errores de validación en la ingesta, campos desconocidos, respuestas 403 o 429, o cuando se pida integrar una fuente nueva.
---

# Fuente de datos

Cada fuente tiene un adaptador aislado en services/core/src/apexpulse/sources/
que guarda el crudo, valida la entrada y emite eventos canónicos v1
(docs/modelo-de-eventos.md). Ninguna otra parte del código conoce el formato de una fuente
(ADR 0002).

## Contrato
~~~python
class SourceAdapter(Protocol):          # sources/base.py
    name: str  # "openf1", "f1static", "jolpica", "f1live"
    def fetch(self, session: SessionId, dest: Path, *, force: bool = False) -> FetchReport: ...
    def normalize(self, session: SessionId, raw_root: Path) -> Normalized: ...
~~~
- `dest` es la raíz data/raw. El crudo queda en
  `data/raw/<año>/<sesion>/<fuente>/<endpoint>.jsonl.zst` más `manifest.json`,
  que se escribe al final y marca la descarga como completa.
- `FetchReport` lleva registros por endpoint, requests hechos, si vino de la
  caché y los avisos de validación.
- `normalize` lee solo el crudo (sin red) y devuelve `Normalized`: cabecera
  `SessionMeta`, eventos de apexpulse.model sin ordenar y avisos agrupados por
  motivo. Errores de Pydantic se reportan como `SchemaError`. Ejemplo:
  sources/openf1_normalize.py. Si la fuente no publica el estado de pista,
  derivarlo con `derive_track_status` (sources/trackstatus.py).
- Piezas reutilizables: `RateLimiter` (sources/ratelimit.py) y
  `write_jsonl_zst` / `read_jsonl_zst` (sources/rawstore.py).

## Reglas
- El crudo se guarda siempre, comprimido, antes de normalizar: permite
  reprocesar cuando cambia el parser.
- Validación estricta: un campo desconocido se registra como aviso con una
  muestra; un campo obligatorio faltante hace fallar la ingesta. Los campos
  viven en `SCHEMAS` de cada adaptador.
- Límites: OpenF1 3 req/s y 30 req/min; Jolpica 4 req/s y 500 req/h. Usar
  `RateLimiter` con `state_file` en data/state/ para que varias ejecuciones
  compartan el presupuesto. Backoff exponencial ante 429, 5xx o error de red,
  respetando Retry-After.
- Los tests nunca usan la red: tests/conftest.py bloquea los sockets. Se
  prueban con respuestas grabadas servidas por `httpx.MockTransport`.
- Nunca descargar del archivo estático de F1 desde CI ni desde la nube
  (bloqueo de IPs). En CI se usan fixtures.
- Nunca usar credenciales de F1 TV.

## Fuente nueva
1. Documentar en docs/fuentes-de-datos.md: URL base, autenticación, límites,
   términos de uso y cobertura temporal.
2. Escribir en el mismo documento la tabla de mapeo de cada campo de origen
   al evento canónico (ejemplo: sección "Mapeo a eventos canónicos" de OpenF1).
3. Grabar respuestas reales chicas, recortadas a pocos registros y sin
   modificar, en fixtures/sessions/<id>/<fuente>/ (menos de 2 MB), con un
   README que diga de dónde salen y cuándo se grabaron.
4. Implementar el adaptador y su test de contrato en
   services/core/tests/contract/test_<fuente>.py. Ejemplos completos:
   test_openf1.py (caché, límite de tasa, 429, esquema, sesión no disponible)
   y test_openf1_normalize.py (normalización con un tramo real con SC).
5. Si la fuente usa otro nombre de circuito, sumar la columna en
   services/core/src/apexpulse/config/circuits.toml.
6. Cerrar con el skill cambio-documentado.

## Cambio de esquema
1. Reproducir con el crudo guardado en data/raw
   (`make normalize SESSION=<id>`) y leer los avisos del `FetchReport`, del
   manifiesto o de la normalización.
2. Guardar la muestra que falla como fixture nuevo.
3. Ajustar `SCHEMAS` y el parser manteniendo compatibilidad con el formato
   anterior si ambos conviven.
4. Si cambia un evento canónico, subir la versión del esquema siguiendo
   docs/modelo-de-eventos.md.
5. Registrar el incidente en docs/runbook.md, sección "Fuentes de datos":
   síntoma, causa y corrección.

## Diagnóstico rápido
| Síntoma                                  | Causa probable                   | Acción                                  |
|------------------------------------------|----------------------------------|-----------------------------------------|
| `campos desconocidos: x=...`             | La fuente agregó un campo        | Sumarlo a `known` en `SCHEMAS`          |
| `el registro 0 no tiene x`               | Campo renombrado o eliminado     | Pasos de "Cambio de esquema"            |
| `HTTP 429 tras 6 intentos`               | Límite superado (otra ejecución) | Esperar un minuto; revisar data/state/  |
| `queda disponible desde ...`             | Sesión no terminó o es reciente  | Reintentar 30 min después del final     |
| `no tiene una sesión ... Circuitos ...`  | circuit_short_name distinto      | Corregir config/circuits.toml           |
| 403 desde CI o la nube                   | Bloqueo de IPs de cloud          | Descargar solo desde IP residencial     |

## Fuente de verdad
docs/fuentes-de-datos.md, docs/modelo-de-eventos.md, docs/runbook.md y
services/core/src/apexpulse/sources/.
