---
name: nueva-lectura
description: Agrega o modifica una regla del motor de lecturas de ApexPulse (undercut, parada barata, degradación, batalla, condiciones u otra nueva), su plantilla de texto en español, sus umbrales y sus tests. Usar cuando la tarea mencione lecturas, reglas, insights, umbrales o textos que el usuario ve durante la carrera.
---

# Nueva lectura

Una lectura es una conclusión verificable con evidencia numérica. Es determinística: la
misma secuencia de eventos produce las mismas lecturas. El catálogo de reglas, la definición
de parada real y el estado de calibración de cada umbral están en docs/lecturas.md.

## Archivos
- Regla: services/core/src/apexpulse/readings/<id>.py (una por archivo).
- Registro: la lista `rules` de `Engine.__init__` en readings/engine.py (el orden importa:
  fija el orden de las lecturas dentro de un mismo evento).
- Plantilla: services/core/src/apexpulse/config/mensajes_es.toml.
- Umbrales: services/core/src/apexpulse/config/readings.toml, con su carga y validación en
  readings/config.py.
- Tests: services/core/tests/test_readings.py.
- Golden: llega en H1 tarea 8 (`make golden`). Hasta entonces los cambios de texto o de umbral
  se prueban en test_readings.py con textos exactos.
- Documentación: docs/lecturas.md.

## Contrato
```python
class Rule(Protocol):
    id: str        # "undercut_window"; estable, lo usan los keys, los golden y la UI
    version: int   # se incrementa si cambia la lógica
    def reset(self) -> None: ...
    def on_event(self, evento: Event, state: RaceState, ctx: Context) -> list[Reading]: ...
```
`on_event` recibe cada evento ya aplicado a `RaceState`, en el orden del replay. `ctx.stops`
es el seguimiento de paradas reales y `ctx.new_stops` las confirmadas con este evento.
Una `Reading` lleva rule, key estable, t (instante del evento que la emite), lap (vuelta del
líder que describe el texto), drivers, evidence (nombre, valor y unidad) y text.

## Reglas del motor
- Causal: usar solo el estado y los eventos ya recibidos. Nada de mirar hacia adelante, reloj
  ni azar.
- Seek: la memoria de la regla es un fold de los eventos. `reset()` la deja en el estado
  inicial; el replay re-pliega en silencio los eventos salteados. Si una regla guarda algo
  fuera de `reset()`, el seek rompe la igualdad con la reproducción continua.
- Una lectura por situación: el `key` identifica la situación (regla, pilotos, vuelta o stint)
  y no cambia si cambia el texto.
- Evidencia solo observable. El texto no afirma lo que el modelo no mide (por ejemplo, tiempo
  ahorrado).
- Para saber si hubo una parada real usar `ctx.stops`, no `stationary_s` ni el número de
  stint por separado: OpenF1 se comporta distinto en cada carrera (docs/lecturas.md).

## Pasos
1. Definir la condición en una frase y los umbrales con unidad. Separar las guardas (descartan
   datos que no significan lo que parecen) de los umbrales (dependen de calibración).
2. Poner los umbrales en readings.toml con un comentario de justificación y `calibrated`. Si
   no se calibró con sesiones reales, queda en false y se dice por qué.
3. Escribir la regla y registrarla en `Engine`.
4. Agregar la plantilla con estas reglas de redacción:
   - Español neutro, presente, voz activa.
   - Pilotos con su código de 3 letras.
   - Números con coma decimal y unidad: "19,8 s".
   - Sin adjetivos de relleno ni afirmaciones que la evidencia no sostenga.
5. Elegir una sesión donde la situación ocurrió de verdad. Si no hay fixture, recortarla con
   `make fixture` (skill sesion-replay), que arrastra el último registro previo de cada piloto.
6. Tests: una rama por condición y por guarda con eventos sintéticos, el caso real con texto
   exacto, y el test de seek (mismas lecturas que la reproducción continua, sin repetir las
   anteriores). Correr `make replay SESSION=<id> NOWAIT=1` y leer las líneas LECTURA.
7. Documentar en docs/lecturas.md: condición, umbrales con su estado de calibración,
   plantilla y un ejemplo real con vuelta y sesión.
8. Cerrar con el skill cambio-documentado.

## Ejemplo de plantilla
```toml
[cheap_stop]
detenido = "{piloto} para bajo {estado} en la vuelta {vuelta}: {detenido} s detenido{carril}."
```

## Fuente de verdad
docs/lecturas.md y docs/modelo-de-eventos.md.
