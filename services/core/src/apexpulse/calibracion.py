"""Calibración de `undercut_window`: intentos reales de undercut, independientes de la lectura.

`make calibrar` mide el resultado de cada parada real (definición de `cheap_stop`/`StopTracker`,
no `stop_duration` crudo) contra el auto que iba inmediatamente adelante, sin importar si la
regla actual habría emitido una lectura. Así se puede elegir `max_gap_s` y `min_tyre_age_laps`
por el resultado observado, no por si la regla con los umbrales de hoy los habría marcado.

Categorías de un intento (una por cada parada real de P, con R el auto adelante en el instante
anterior a la parada):

- `sin_rival_comparable`: no hay R, o no pasa las guardas de calidad de dato que ya usa la regla
  (doblado, vuelta de entrada o salida de boxes, parada reciente). No es parte de la calibración.
- `ya_habia_parado`: R ya hizo una parada real entre la parada anterior de P (o el inicio de la
  carrera) y esta. R se movió primero en este ciclo: ni éxito ni fracaso.
- `escalado`: R para de verdad dentro de `K` vueltas de la parada de P. Categoría puntuada:
  éxito si P queda adelante de R cuando los dos ya volvieron a pista (completaron su vuelta de
  salida); si no, fracaso real (paró, R respondió, no alcanzó para pasar).
- `no_respondio_en_k`: R no para dentro de `K` vueltas (sea porque para más tarde o porque no
  vuelve a parar en la carrera). No es fracaso de la regla, sale de la métrica principal; se
  guarda un resultado de referencia a un horizonte fijo (`Lp + K`, vueltas propias de P) para la
  sensibilidad con y sin esta categoría.
- `no_evaluable`: pasa los filtros anteriores pero falta el dato para comparar (la vuelta de
  salida de alguno no se completó, por ejemplo un retiro). Rara, se cuenta aparte.

La comparación de posición usa `position` (el lugar en la carrera), no el hueco puntual contra el
rival: un tercer auto que se cruza entre P y R en el instante de la comparación cuenta como que
el undercut no funcionó aunque P sea más rápido. Es ruido conocido, no corregido.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from apexpulse.model import (
    Event,
    LapCompleted,
    PositionChanged,
    StintStarted,
    read_events,
    sort_key,
)
from apexpulse.readings.config import Messages, ReadingsConfig, load_config, load_messages
from apexpulse.readings.stops import StopTracker
from apexpulse.readings.undercut import Evaluation, UndercutWindow
from apexpulse.replay.state import RaceState


class Categoria(StrEnum):
    ESCALADO = "escalado"
    YA_HABIA_PARADO = "ya_habia_parado"
    NO_RESPONDIO_EN_K = "no_respondio_en_k"
    SIN_RIVAL_COMPARABLE = "sin_rival_comparable"
    NO_EVALUABLE = "no_evaluable"


@dataclass(frozen=True)
class Intento:
    """Un intento de undercut: una parada real de `perseguidor`, evaluada contra `rival`."""

    sesion: str
    perseguidor: int
    rival: int | None
    vuelta_parada: int  # Lp
    categoria: Categoria
    gap_previo: float | None = None
    edad_perseguidor: int | None = None
    edad_rival: int | None = None
    exito: bool | None = None  # solo `escalado`
    exito_horizonte: bool | None = None  # solo `no_respondio_en_k`, proxy a Lp+K


def _salida(stints: list[StintStarted], vuelta_parada: int) -> int | None:
    """Vuelta en que arranca el stint nuevo de la parada en `vuelta_parada`; None si no llegó."""
    candidatos = sorted(s.lap for s in stints if s.lap >= vuelta_parada)
    return candidatos[0] if candidatos else None


def _posicion_en(historial: list[tuple[datetime, int | None]], t: datetime) -> int | None:
    """Última posición conocida en o antes de `t`; None si no hay ninguna."""
    i = bisect_right(historial, (t, math.inf)) - 1
    return None if i < 0 else historial[i][1]


def _nuevo_intento(
    nombre: str,
    p: int,
    r: int | None,
    lp: int,
    categoria: Categoria,
    gap_previo: float | None,
    edad_p: int | None,
    edad_r: int | None,
    *,
    exito: bool | None = None,
    exito_horizonte: bool | None = None,
) -> Intento:
    return Intento(nombre, p, r, lp, categoria, gap_previo, edad_p, edad_r, exito, exito_horizonte)


def analizar_sesion(
    parquet: Path,
    *,
    k: int,
    sesion: str | None = None,
    config: ReadingsConfig | None = None,
    messages: Messages | None = None,
) -> list[Intento]:
    """Extrae los intentos de undercut de una sesión ya normalizada (`data/canonical/<id>.parquet`).

    `config` fija las guardas sin calibrar (`min_lap`, `recent_stop_laps`, `confirm_timeout_laps`)
    en sus valores actuales de `readings.toml`: no son parte de esta calibración. `max_gap_s` y
    `min_tyre_age_laps` de `config` no se usan (la calibración mide el intento completo, no si la
    regla de hoy lo habría abierto).
    """
    config = config or load_config()
    messages = messages or load_messages()
    nombre = sesion or parquet.stem

    eventos: list[Event] = sorted(read_events(parquet), key=sort_key)
    state = RaceState()
    tracker = StopTracker(config.stops.confirm_timeout_laps)
    uw = UndercutWindow(config.undercut, messages)

    snapshots: dict[tuple[int, int], Evaluation] = {}
    lap_time: dict[tuple[int, int], datetime] = {}
    ultima_vuelta: dict[int, datetime] = {}
    stints: dict[int, list[StintStarted]] = defaultdict(list)
    posiciones: dict[int, list[tuple[datetime, int | None]]] = defaultdict(list)

    for evento in eventos:
        state.apply(evento)
        tracker.observe(evento, state)
        if isinstance(evento, StintStarted):
            stints[evento.driver].append(evento)
        elif isinstance(evento, LapCompleted):
            lap_time[(evento.driver, evento.lap)] = evento.t
            ultima_vuelta[evento.driver] = evento.t
            ev = uw.evaluate(evento.driver, state, tracker)
            if ev is not None:
                snapshots[(evento.driver, evento.lap)] = ev
        elif isinstance(evento, PositionChanged):
            for d, auto in state.cars.items():
                historial = posiciones[d]
                if not historial or historial[-1][1] != auto.position:
                    historial.append((evento.t, auto.position))

    intentos: list[Intento] = []
    for p, paradas in tracker.stops.items():
        anterior = 0  # vuelta de la parada previa de P, 0 si es la primera
        for parada in sorted(paradas, key=lambda s: s.pit_lap):
            lp = parada.pit_lap
            ev = snapshots.get((p, lp - 1))
            if ev is None or not ev.guards_ok:
                rival_o_nada = ev.rival if ev else None
                intentos.append(
                    _nuevo_intento(
                        nombre,
                        p,
                        rival_o_nada,
                        lp,
                        Categoria.SIN_RIVAL_COMPARABLE,
                        None,
                        None,
                        None,
                    )
                )
                anterior = lp
                continue
            r = ev.rival
            gap_previo, edad_p, edad_r = ev.gap_s, ev.chaser_age, ev.rival_age

            paradas_r = sorted(s.pit_lap for s in tracker.stops.get(r, []))
            if any(anterior < lr < lp for lr in paradas_r):
                intentos.append(
                    _nuevo_intento(
                        nombre, p, r, lp, Categoria.YA_HABIA_PARADO, gap_previo, edad_p, edad_r
                    )
                )
                anterior = lp
                continue

            futuras_r = [lr for lr in paradas_r if lr > lp]
            respuesta_r = futuras_r[0] if futuras_r and futuras_r[0] <= lp + k else None
            if respuesta_r is not None:
                salida_p = _salida(stints[p], lp)
                salida_r = _salida(stints[r], respuesta_r)
                t_p = lap_time.get((p, salida_p)) if salida_p is not None else None
                t_r = lap_time.get((r, salida_r)) if salida_r is not None else None
                t_rejoin = max(t_p, t_r) if t_p is not None and t_r is not None else None
                pos_p = _posicion_en(posiciones[p], t_rejoin) if t_rejoin is not None else None
                pos_r = _posicion_en(posiciones[r], t_rejoin) if t_rejoin is not None else None
                if pos_p is None or pos_r is None:
                    intentos.append(
                        _nuevo_intento(
                            nombre, p, r, lp, Categoria.NO_EVALUABLE, gap_previo, edad_p, edad_r
                        )
                    )
                else:
                    intentos.append(
                        _nuevo_intento(
                            nombre,
                            p,
                            r,
                            lp,
                            Categoria.ESCALADO,
                            gap_previo,
                            edad_p,
                            edad_r,
                            exito=pos_p < pos_r,
                        )
                    )
            else:
                # Horizonte fijo Lp+K en vueltas propias de P; si no llegó a completarlas, se usa
                # su último instante conocido (retiro o fin de carrera antes de esa vuelta).
                t_horizonte = next(
                    (lap_time[(p, v)] for v in range(lp + k, lp, -1) if (p, v) in lap_time),
                    ultima_vuelta.get(p),
                )
                exito_h = None
                if t_horizonte is not None:
                    pos_p = _posicion_en(posiciones[p], t_horizonte)
                    pos_r = _posicion_en(posiciones[r], t_horizonte)
                    if pos_p is not None and pos_r is not None:
                        exito_h = pos_p < pos_r
                intentos.append(
                    _nuevo_intento(
                        nombre,
                        p,
                        r,
                        lp,
                        Categoria.NO_RESPONDIO_EN_K,
                        gap_previo,
                        edad_p,
                        edad_r,
                        exito_horizonte=exito_h,
                    )
                )
            anterior = lp
    return intentos


# Reporte ---------------------------------------------------------------------------------------
# N mínimo y candidatos fijados de antemano (docs/lecturas.md), antes de ver el resultado.

N_MINIMO = 8
GAP_CANDIDATOS: tuple[float, ...] = (1.0, 1.5, 2.0, 2.5, 3.0)
EDAD_CANDIDATOS: tuple[int, ...] = (5, 10, 15)
GAP_BORDES: tuple[tuple[float, float | None], ...] = (
    (0.0, 1.0),
    (1.0, 2.0),
    (2.0, 3.0),
    (3.0, None),
)
DIFERENCIA_EDAD_NIVELES: tuple[int, ...] = (0, 1, 3)  # 0 = sin filtro

_Z95 = 1.959963984540054


def wilson(aciertos: int, n: int, z: float = _Z95) -> tuple[float, float]:
    """Intervalo de Wilson al 95 % (por defecto) para una proporción de `aciertos` en `n`."""
    p = aciertos / n
    denominador = 1 + z**2 / n
    centro = (p + z**2 / (2 * n)) / denominador
    margen = (z / denominador) * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return (max(0.0, centro - margen), min(1.0, centro + margen))


@dataclass(frozen=True)
class Celda:
    """Una celda de las tablas: n, aciertos, tasa e intervalo de Wilson.

    `suficiente` es False si `n < N_MINIMO`: la tasa y el intervalo igual se calculan (para no
    perder el dato), pero el reporte los marca "insuficiente" en vez de mostrarlos como si fueran
    una medición confiable.
    """

    n: int
    aciertos: int
    tasa: float | None
    intervalo: tuple[float, float] | None
    suficiente: bool


def celda(aciertos: int, n: int, *, n_minimo: int = N_MINIMO) -> Celda:
    if n == 0:
        return Celda(0, 0, None, None, False)
    return Celda(n, aciertos, aciertos / n, wilson(aciertos, n), n >= n_minimo)


def escalados(intentos: list[Intento]) -> list[Intento]:
    return [i for i in intentos if i.categoria is Categoria.ESCALADO]


def resumen_categorias(intentos: list[Intento]) -> Counter[Categoria]:
    return Counter(i.categoria for i in intentos)


def _aciertos(lista: list[Intento]) -> int:
    return sum(bool(i.exito) for i in lista)


def cumple_regla(candidato: Celda, complemento: Celda) -> bool:
    """Regla de decisión: ambas celdas con n suficiente, el candidato supera al complemento y
    su intervalo de Wilson no contiene la tasa puntual del complemento (docs/lecturas.md)."""
    if not candidato.suficiente or not complemento.suficiente:
        return False
    assert candidato.tasa is not None and complemento.tasa is not None and candidato.intervalo
    return candidato.tasa > complemento.tasa and candidato.intervalo[0] > complemento.tasa


def tabla_acumulada_gap(
    intentos: list[Intento],
    candidatos: tuple[float, ...] = GAP_CANDIDATOS,
    *,
    n_minimo: int = N_MINIMO,
) -> dict[float, tuple[Celda, Celda]]:
    """Por candidato (gap <= candidato): celda del candidato y de su complemento (gap > candidato).

    El complemento es la línea de base de ese candidato (no una tasa global fija): son los
    intentos escalados que no cumplen ese umbral en particular.
    """
    con_gap = [i for i in escalados(intentos) if i.gap_previo is not None]
    salida: dict[float, tuple[Celda, Celda]] = {}
    for c in candidatos:
        dentro = [i for i in con_gap if i.gap_previo is not None and i.gap_previo <= c]
        fuera = [i for i in con_gap if i.gap_previo is not None and i.gap_previo > c]
        salida[c] = (
            celda(_aciertos(dentro), len(dentro), n_minimo=n_minimo),
            celda(_aciertos(fuera), len(fuera), n_minimo=n_minimo),
        )
    return salida


def tabla_acumulada_edad(
    intentos: list[Intento],
    candidatos: tuple[int, ...] = EDAD_CANDIDATOS,
    *,
    n_minimo: int = N_MINIMO,
) -> dict[int, tuple[Celda, Celda]]:
    """Por candidato (edad_perseguidor >= candidato): celda del candidato y de su complemento."""
    con_edad = [i for i in escalados(intentos) if i.edad_perseguidor is not None]
    salida: dict[int, tuple[Celda, Celda]] = {}
    for c in candidatos:
        dentro = [i for i in con_edad if i.edad_perseguidor is not None and i.edad_perseguidor >= c]
        fuera = [i for i in con_edad if i.edad_perseguidor is not None and i.edad_perseguidor < c]
        salida[c] = (
            celda(_aciertos(dentro), len(dentro), n_minimo=n_minimo),
            celda(_aciertos(fuera), len(fuera), n_minimo=n_minimo),
        )
    return salida


def tabla_disjunta_gap(
    intentos: list[Intento],
    bordes: tuple[tuple[float, float | None], ...] = GAP_BORDES,
    *,
    n_minimo: int = N_MINIMO,
) -> dict[tuple[float, float | None], Celda]:
    """Tabla de apoyo, tramos disjuntos de `gap_previo` (diagnóstico, no decide el umbral)."""
    esc = escalados(intentos)
    salida = {}
    for lo, hi in bordes:
        subset = [
            i
            for i in esc
            if i.gap_previo is not None
            and lo <= i.gap_previo < (hi if hi is not None else math.inf)
        ]
        salida[(lo, hi)] = celda(sum(bool(i.exito) for i in subset), len(subset), n_minimo=n_minimo)
    return salida


def tabla_diferencia_edad(
    intentos: list[Intento],
    niveles: tuple[int, ...] = DIFERENCIA_EDAD_NIVELES,
    *,
    n_minimo: int = N_MINIMO,
) -> dict[int, tuple[Celda, Celda]]:
    """Por nivel (`|edad_perseguidor - edad_rival| >= nivel`): candidato y complemento.

    El nivel 0 (sin filtro) no tiene complemento: no hay nada que quede afuera. Se devuelve con
    una celda vacía (n=0) en ese lugar, para que el llamador no la confunda con una medición.
    """
    con_diferencia = [
        (i, abs(i.edad_perseguidor - i.edad_rival))
        for i in escalados(intentos)
        if i.edad_perseguidor is not None and i.edad_rival is not None
    ]
    salida: dict[int, tuple[Celda, Celda]] = {}
    for nivel in niveles:
        if nivel == 0:
            todos = [i for i, _ in con_diferencia]
            salida[nivel] = (celda(_aciertos(todos), len(todos), n_minimo=n_minimo), celda(0, 0))
            continue
        dentro = [i for i, d in con_diferencia if d >= nivel]
        fuera = [i for i, d in con_diferencia if d < nivel]
        salida[nivel] = (
            celda(_aciertos(dentro), len(dentro), n_minimo=n_minimo),
            celda(_aciertos(fuera), len(fuera), n_minimo=n_minimo),
        )
    return salida


def sensibilidad_no_respondio(
    intentos: list[Intento], *, n_minimo: int = N_MINIMO
) -> tuple[Celda, Celda]:
    """Tasa de éxito sin y con los `no_respondio_en_k` evaluables, al horizonte Lp+K."""
    esc = escalados(intentos)
    sin = celda(sum(bool(i.exito) for i in esc), len(esc), n_minimo=n_minimo)
    no_respondio = [
        i
        for i in intentos
        if i.categoria is Categoria.NO_RESPONDIO_EN_K and i.exito_horizonte is not None
    ]
    aciertos_con = sum(bool(i.exito) for i in esc) + sum(
        bool(i.exito_horizonte) for i in no_respondio
    )
    con = celda(aciertos_con, len(esc) + len(no_respondio), n_minimo=n_minimo)
    return sin, con
