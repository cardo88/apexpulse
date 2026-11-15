# Lecturas

Catálogo de las reglas del motor de lecturas (`services/core/src/apexpulse/readings/`): condición, umbrales, plantilla y un ejemplo real de cada una. Una lectura es una conclusión con evidencia numérica; el motor es determinístico: la misma secuencia de eventos produce las mismas lecturas.

Estado al cierre de H1: dos reglas, `cheap_stop` y `undercut_window`. La salida de `cheap_stop` está fijada con golden tests sobre tres carreras; `undercut_window` se cubre con propiedades y no tiene golden hasta calibrar sus umbrales (ver [Golden y propiedades](#golden-y-propiedades)).

## Cómo funciona

- `Engine.process(evento, state)` se llama una vez por evento, ya aplicado a `RaceState`, en el orden del replay. Devuelve las lecturas nuevas. `Replay(engine=Engine.default())` lo integra: cada `Step` trae `readings`, y `make replay` imprime cada una como una línea `LECTURA`.
- **Causal.** Una regla usa solo el estado y los eventos recibidos hasta el evento actual: no mira hacia adelante, no usa el reloj ni azar. Con el mismo `t` valen las prioridades de `KIND_ORDER` (un `pit` llega antes que el `position` y el `interval` del mismo instante, así que usa el último intervalo conocido).
- **Seek.** El estado del motor es un fold de los eventos, igual que `RaceState`. Tras un seek hacia adelante el replay le pasa en silencio los eventos salteados; hacia atrás lo reinicia y re-pliega desde el comienzo. El resultado es el mismo que reproducir de corrido hasta ese punto: las lecturas anteriores al punto de llegada no se repiten, y `Engine.history` las conserva todas para quien necesite la lista completa. Un test lo verifica sobre Mónaco, São Paulo y Australia.
- **Una `Reading`** lleva `rule`, `key` estable (dedupe y golden), `t` (instante del evento que la emite), `lap` (vuelta del líder que describe el texto), `drivers`, `evidence` (nombre, valor y unidad) y `text`. El texto sale de `config/mensajes_es.toml`; los números, de la evidencia.
- **Redacción.** Español neutro, presente, voz activa, códigos de piloto de 3 letras, coma decimal con unidad (`8,6 s`). Los textos no afirman ahorros de tiempo ni juzgan la parada: describen lo observado.

## Parada real

Base de `cheap_stop` y de las guardas de `undercut_window` (`readings/stops.py`). Una pasada por el pit lane (`pit`) es una parada real si:

1. `stationary_s` no es nulo. Se confirma en el momento, sin esperar el stint; o
2. hay un stint nuevo, en la vuelta de la pasada o en la siguiente, con un **juego de neumáticos distinto**.

El juego es distinto si el compuesto cambia (un compuesto `UNKNOWN` no permite comparar), o si el compuesto es el mismo y la edad al empezar es menor que la esperada: la del stint anterior más las vueltas transcurridas entre los dos stints. Un juego que sigue puesto llega con la edad esperada exacta. Si falta la edad, decide solo el compuesto (el normalizador omite hoy los stints sin `tyre_age_at_start`, así que en la práctica la edad siempre está). El primer stint de un piloto no es un cambio.

¿Por qué no basta "stint nuevo en la vuelta siguiente"? OpenF1 no es uniforme:

| Carrera | `lap_start` del stint nuevo | Efecto |
|---------|-----------------------------|--------|
| São Paulo 2026 | La vuelta siguiente a la pasada (`lap_number` + 1) en las 58 pasadas | La regla simple da 5 de 5 en las pasadas sin `stop_duration` |
| Mónaco 2026 | La misma vuelta de la pasada | La regla simple pierde paradas normales (LEC v35, ANT v37, PIA v48) |
| Mónaco bajo SC | Un stint por cada pasada aunque el juego no cambie (HAM v61 y v66) | La regla simple da falsos positivos, como HUL v58 (20,5 s en el pit lane, mismo juego) |

Si la confirmación depende de un stint que todavía no llegó, queda **diferida**: se recuerda la pasada y se emite al llegar el `StintStarted`. Si el piloto completa la vuelta `pasada + confirm_timeout_laps` sin que llegue, la confirmación vence sin emitir. Una pasada nueva del mismo piloto reemplaza a la que seguía pendiente. La lectura lleva el instante de la pasada y el de la confirmación (`instante_pasada` e `instante_confirmacion`); su `key` usa la vuelta de la pasada.

Verificación contra datos reales (tests en `tests/test_readings.py`):

- Las 5 pasadas de São Paulo sin `stationary_s` (HAD v16, VER v17, ALO v17, COL v53 y HAD v62) son paradas reales por stint; en total, 58 paradas reales de 58 pasadas.
- HUL v58 en Mónaco no es una parada real: la confirmación diferida vence.

## `cheap_stop`: parada bajo Safety Car o VSC

**Condición.** Una parada real cuya pasada por el pit lane ocurrió con el estado de pista en `SC`, `SC_ENDING`, `VSC` o `VSC_ENDING` (`NEUTRALIZED`). Con bandera roja no dispara: el cambio de neumáticos es libre y la parada no es comparable. Se emite una vez por pasada (`cheap_stop:<piloto>:<vuelta de la pasada>`).

**Umbrales.** Ninguno propio. Depende de `[stops] confirm_timeout_laps`.

**Evidencia.** Solo lo observado: estado de pista, vuelta propia, instante de la pasada y de la confirmación, criterio (`detencion` o `stint`), `pit_lane_s` y `detenido_s`; si la parada se confirmó por stint, también `compuesto` y `edad_neumatico`. No hay estimación de tiempo ahorrado: requiere el ritmo del pelotón y la geometría del pit lane de cada circuito, que el modelo no tiene.

**Plantillas** (`config/mensajes_es.toml`):

- Con detención: `{piloto} para bajo {estado} en la vuelta {vuelta}: {detenido} s detenido{carril}.`
- Por stint: `{piloto} cambia neumáticos bajo {estado} en la vuelta {vuelta}: {compuesto} con {edad} vueltas de uso{carril}.`

`{vuelta}` es la vuelta del líder en la pasada; `{carril}` es ` y {lane_s} s en pit lane` cuando hay dato.

**Ejemplos reales** (`make replay SESSION=<id> NOWAIT=1`):

```text
14:21:26  v61  LECTURA    HAM para bajo Safety Car en la vuelta 61: 8,6 s detenido y 31,2 s en pit lane.
14:22:10  v61  LECTURA    BOR cambia neumáticos bajo Safety Car en la vuelta 61: blandos con 0 vueltas de uso y 20,3 s en pit lane.
```

Mónaco 2026 (`2026-monaco-r`, SC de la vuelta 60): las 5 paradas con detención (HAM, ALO, RUS, PER, BOR) y 3 cambios confirmados por stint. En Australia (`2026-australia-r`, tres VSC en las vueltas 12, 18 y 34) salen 10, 4 y 1 lecturas:

```text
04:19:43  v12  LECTURA    NOR para bajo VSC en la vuelta 12: 2,9 s detenido y 18,3 s en pit lane.
04:31:12  v19  LECTURA    VER cambia neumáticos bajo VSC en la vuelta 19: medios con 0 vueltas de uso y 19,1 s en pit lane.
```

**Casos verificados** (golden en `tests/golden/`, detalle en [Golden y propiedades](#golden-y-propiedades)):

| Sesión | Período | Lecturas | Qué demuestra |
|--------|---------|----------|---------------|
| Mónaco | SC de la vuelta 60 y de la 66 | 8 | 5 paradas con detención y 3 cambios por stint, todas bajo `SC` |
| Australia | VSC de la vuelta 12 | 10 | Positivo: paradas con detención bajo `VSC` |
| Australia | VSC de la vuelta 18 | 4 | Positivo: 3 con detención y 1 por stint (VER, sin `stop_duration`) |
| Australia | VSC de la vuelta 34 | 1, de borde | Sin paradas bajo `VSC` pleno; ver abajo |
| São Paulo | Sin SC ni VSC | 0 | Negativo: con bandera verde no hay lectura aunque haya 58 paradas |

**Caso de borde de la vuelta 34 en Australia.** El VSC se desplegó a las 04:52:20, `VSC ENDING` llegó a las 04:52:58 y `TRACK CLEAR` a las 04:53:11. BOR pasó por el pit lane a las 04:53:09 (5,2 s detenido), con el estado todavía en `VSC_ENDING`, que cuenta como neutralización: sale una lectura (`BOR para bajo VSC en la vuelta 34`). No es un negativo limpio: durante el VSC pleno no hubo paradas, pero la pasada ocurrió 2 s antes del verde. Decidir si `*_ENDING` debe contar queda para H2.

**Dato de OpenF1 que el golden fija tal cual.** En Australia 10 de 26 pasadas del endpoint `pit` traen un `lap_number` que no corresponde a la vuelta del piloto en ese instante (46 para las cinco paradas de la vuelta 12; 18 para BOR en la 34). El texto no se ve afectado (usa la vuelta del líder), pero sí la `key` (`cheap_stop:1:46`) y la evidencia `vuelta_propia`. Mónaco y São Paulo no tienen el problema (0 de 86 y 0 de 58). El golden conserva los valores crudos; corregirlos desde `laps` es de H2 y cambiará el golden de Australia.

## `undercut_window`: ventana de undercut

**Condición.** Cuando un auto completa una vuelta, se lo evalúa contra el que va inmediatamente adelante según las posiciones. La ventana se abre si, en `confirm_laps` vueltas seguidas, se cumplen todas estas condiciones; se emite una vez por pareja y stint del perseguidor (`undercut_window:<perseguidor>:<rival>:<stint>`):

| Tipo | Condición |
|------|-----------|
| Guarda | El intervalo del perseguidor es numérico: un auto doblado no tiene `interval_s`, y si el rival está doblado la distancia no es en pista |
| Guarda | Ni el perseguidor ni el rival están en vuelta de entrada o de salida de boxes (incluye un stint que todavía no completó vuelta) |
| Guarda | Ni el perseguidor ni el rival pararon de verdad en las últimas `recent_stop_laps` vueltas |
| Guarda | El perseguidor completó al menos la vuelta `min_lap` (configurable; con 1 se desactiva) |
| Umbral | Pista en verde |
| Umbral | `interval_s` de `max_gap_s` o menos |
| Umbral | Edad del neumático del perseguidor de `min_tyre_age_laps` vueltas o más (vueltas de uso al completar la vuelta) |

Las guardas descartan datos que no significan lo que parecen y no dependen de calibración. Los umbrales sí.

**Evidencia.** `gap_s`, `vueltas_seguidas`, `posicion_perseguidor`, `vuelta_perseguidor` (última vuelta que completó), edad y compuesto de cada auto. La regla está en la versión 2 (guarda `min_lap` y `vuelta_perseguidor`).

**Plantilla.** `{perseguidor} está a {gap} s de {rival} desde hace {vueltas} vueltas, con neumáticos {compuesto_p} de {edad_p} vueltas contra {compuesto_r} de {edad_r}: ventana de undercut.`

**Ejemplo real** (`2026-australia-r`):

```text
04:24:47  v15  LECTURA    BOR está a 1,6 s de BEA desde hace 2 vueltas, con neumáticos medios de 14 vueltas contra medios de 14: ventana de undercut.
```

### Lecturas en las primeras vueltas

Se midió sobre las tres carreras completas (`data/`, no versionadas). La regla **no emite nada antes de la vuelta 12**: la primera lectura sale en la vuelta 12 en Mónaco y São Paulo y en la 15 en Australia. Lo que se ve como "ruido temprano" es la primera tanda, antes de las primeras paradas.

**Origen de la edad.** La edad del neumático no es un artefacto: sale de `tyre_age_at_start` del endpoint `stints` de OpenF1 (`StintStarted.tyre_age`) más las vueltas que el piloto lleva en el stint (`_edad` en `readings/undercut.py`). Ejemplo, São Paulo, vuelta 12:

```text
17:19:47  v12  LECTURA    LIN está a 0,9 s de BEA desde hace 2 vueltas, con neumáticos intermedios de 11 vueltas contra intermedios de 11: ventana de undercut.
```

El stint 1 de LIN es `lap_start = 1`, `tyre_age_at_start = 0`, intermedios. Al completar la vuelta 11 lleva 0 + (11 − 1 + 1) = 11 vueltas, y la regla ya la venía cumpliendo en la 10. En un primer stint con juego nuevo la edad es el número de vuelta: `min_tyre_age_laps = 10` más `confirm_laps = 2` fijan el piso en la 12. Los 64 primeros stints de las tres carreras parten con edad 0 (Mónaco 22, São Paulo 22, Australia 20): hoy ninguna carrera de prueba tiene un juego usado en la largada, que es el caso que la guarda `min_lap` cubre.

**Es legítimo.** Los datos son correctos, y la situación existe: en Mónaco el mismo tren de autos sigue pegado hasta la vuelta 22, y las lecturas de las vueltas 12 a 15 en São Paulo y Australia son los autos que van a parar a continuación. Lo que sí es débil es la señal: en 15 de las 34 lecturas de São Paulo (6 de 13 en Mónaco, 4 de 7 en Australia) ambos autos llevan la misma edad y el mismo compuesto, y en 33 de 34 el mismo compuesto, así que no hay ventaja de neumáticos que explotar. Es un asunto de calibración (por ejemplo, exigir diferencia de edad con el rival), no de la edad.

**Guarda `min_lap`.** Se agregó una guarda de vuelta mínima del perseguidor, configurable en `[undercut_window] min_lap`. Protege del comienzo de carrera, donde el intervalo corto lo explica la largada y un juego usado puede cumplir la edad desde la vuelta 3. El valor por defecto es 5 y no cambia la salida de estas carreras. Subirlo **retrasa** una lectura hasta que la racha se cumple desde `min_lap` (en Mónaco, con `min_lap = 20` las cuatro lecturas de la vuelta 12 salen en la 22, las mismas parejas), y quita las que dejan de cumplirse (pit stops):

| `min_lap` | Mónaco (78 vueltas) | São Paulo (71) | Australia (58) |
|-----------|---------------------|----------------|----------------|
| 1 (sin guarda) | 13 | 34 | 7 |
| 5 (por defecto) | 13 | 34 | 7 |
| 12 | 13 | 32 | 7 |
| 15 | 13 | 22 | 5 |
| 20 | 13 | 22 | 5 |

No se subió el valor para limpiar la salida: sería calibrar con las mismas tres carreras que fijan el golden, y las vueltas 12 a 15 son justo la ventana previa a la primera parada. Queda para H2.

**La regla no conoce las vueltas que quedan.** `SessionMeta` no trae el total de la carrera, así que la regla puede abrir una ventana a pocas vueltas de la bandera a cuadros, donde un undercut ya no tiene sentido. Queda pendiente (agregar el total de vueltas al modelo o a la configuración del circuito).

## Umbrales: todos sin calibrar

Los valores viven en `config/readings.toml`, cada sección con `calibrated = false`. Son criterios iniciales razonados, no resultados medidos. Cambiar un valor cambia la salida y pasa por golden tests.

| Umbral | Valor | Justificación inicial |
|--------|-------|-----------------------|
| `[stops] confirm_timeout_laps` | 2 | Una vuelta de margen sobre São Paulo, donde el stint llega al empezar la vuelta siguiente a la pasada |
| `[undercut_window] max_gap_s` | 2,0 s | Dentro de 2 s el perseguidor sigue en el aire sucio del rival; en 2026 no hay DRS, así que no hay un umbral de 1 s |
| `[undercut_window] min_tyre_age_laps` | 10 | Con juegos jóvenes la degradación todavía no da ventaja a un juego nuevo. Criterio físico sin respaldo en datos: en São Paulo las primeras paradas son a las 14 vueltas de uso, pero Mónaco tiene paradas verdes en las vueltas 3, 4 y 9 |
| `[undercut_window] confirm_laps` | 2 | Evita avisar por un acercamiento de una vuelta |
| `[undercut_window] min_lap` | 5 | Guarda contra el comienzo de carrera. No cambia la salida de las tres carreras de prueba; ver [Lecturas en las primeras vueltas](#lecturas-en-las-primeras-vueltas) |
| `[undercut_window] recent_stop_laps` | 3 | Un juego recién puesto no tiene el desgaste que hace útil el undercut, y tras una parada el intervalo todavía se está asentando |

**Por qué no hay calibración todavía.** En São Paulo y Mónaco completas hay 15 parejas (perseguidor y rival) en que el perseguidor para con bandera verde y el rival para dentro de las 5 vueltas siguientes. Las paradas se concentran en una tanda, así que casi todos los undercut "se logran" a cualquier distancia (en São Paulo, 11 de 11): la muestra no discrimina umbrales. Se recalibra con Australia y el golden de H2.

**Cuántas de esas 15 parejas pasan las guardas.** 3 de 15. Ninguna llega a abrir la ventana con los umbrales.

| Resultado | Parejas | Detalle |
|-----------|---------|---------|
| Pasan las guardas | 3 | LAW en São Paulo (gap 26 s) y BOT y PER en Mónaco (1 vuelta de uso) |
| Descartadas por una guarda | 4 | 3 con intervalo no numérico (auto doblado) y 1 en vuelta de boxes |
| El líder, sin rival adelante | 1 | |
| No evaluables | 7 | Al completar su última vuelta el perseguidor tenía otro rival adelante que el de la pasada: las tandas de paradas reordenan la pista |

Son 8 evaluables de 15; de ellas, 5 quedan fuera por las guardas o por no tener rival. La medición usa las sesiones completas (`data/`, no versionadas).

**Ruido observado.** Sobre las sesiones completas, `undercut_window` emite 13 lecturas en Mónaco, 34 en São Paulo y 7 en Australia. Ninguna sale antes de la vuelta 12 (ver [Lecturas en las primeras vueltas](#lecturas-en-las-primeras-vueltas)); las de las últimas vueltas (Mónaco 73 a 78) las explica que la regla no conoce el total de vueltas. Es consecuencia de umbrales sin calibrar y se revisa en H2.

## Golden y propiedades

Qué garantiza cada nivel, en `services/core/tests/`:

| Archivo | Garantía |
|---------|----------|
| `test_golden.py` y `golden/*.cheap_stop.json` | La salida completa de `cheap_stop` (clave, instante, vuelta, evidencia y texto) sobre Mónaco, Australia y São Paulo no cambia sin que alguien lo decida |
| `test_propiedades.py` | `undercut_window`: causalidad, una lectura por pareja y stint, estabilidad tras seek y respeto de `min_lap` |
| `test_pipeline.py` | Dos corridas desde los fixtures (descarga simulada, normalización, Parquet, replay y CLI) dan salida idéntica, hasta en los bytes del Parquet |
| `test_readings.py` | Cada rama y guarda con eventos sintéticos, y los casos reales con texto exacto |

**Por qué `undercut_window` no tiene golden.** Sus umbrales están sin calibrar: fijar hoy su salida congelaría 54 lecturas que se van a mover en H2. Las propiedades valen igual después de calibrar. El golden se agrega con la calibración.

**Regenerar un golden.** Solo con un motivo y revisando el diff completo; el motivo va en el mensaje del commit:

```bash
make golden-update                      # los tres
make golden-update SESSION=2026-monaco-r
git diff services/core/tests/golden
```

El test normal nunca escribe: si la salida cambia, falla y apunta a `make golden-update`. Cambiar un texto de `mensajes_es.toml` o un umbral de `readings.toml` rompe el golden de las lecturas que toca, a propósito.

**Propiedades, en una línea cada una.**

- *Causalidad*: cortar la secuencia de eventos en k da exactamente las lecturas que la secuencia completa emitió antes de k.
- *Una lectura por pareja y stint*: ninguna clave repetida ni dos lecturas con los mismos pilotos y stint del perseguidor.
- *Estabilidad tras seek*: llegar a un punto por seek (adelante o atrás) y seguir da lo mismo que reproducir de corrido, sin repetir lo anterior.
- *Vuelta mínima*: con `min_lap = N`, toda lectura tiene `vuelta_perseguidor >= N`.

Si están las sesiones completas en `data/canonical` (compu del autor), las propiedades también corren sobre ellas; en CI se saltean.

## Archivos

| Archivo | Contenido |
|---------|-----------|
| `readings/engine.py` | `Engine`, `Rule` y `Context` |
| `readings/stops.py` | Seguimiento de paradas reales (`StopTracker`) y `juego_distinto` |
| `readings/cheap_stop.py`, `readings/undercut.py` | Las reglas |
| `readings/model.py` | `Reading` y `Evidence` |
| `readings/config.py` | Carga y validación de la configuración y de los textos |
| `tests/golden/` | Salida esperada de `cheap_stop` por sesión (JSON); se regraba con `make golden-update` |
| `config/readings.toml` | Umbrales, con su justificación y el estado de calibración |
| `config/mensajes_es.toml` | Plantillas en español, compuestos y estados de pista |

El procedimiento para agregar o ajustar una regla está en el skill `nueva-lectura`.
