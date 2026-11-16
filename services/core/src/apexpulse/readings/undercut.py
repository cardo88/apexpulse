"""Regla `undercut_window`: un auto lleva varias vueltas pegado al de adelante.

Se evalúa cuando el perseguidor completa una vuelta, con la última distancia conocida. La ventana
se abre cuando, durante `confirm_laps` vueltas seguidas, se cumplen las condiciones. Se emite una
vez por pareja y stint del perseguidor.

Guardas que no dependen de calibración (descartan datos que no significan lo que parecen, o
situaciones donde un undercut ya no tiene sentido):
- el intervalo del perseguidor es numérico: un auto doblado no tiene `interval_s`, y si el rival
  está doblado la distancia no es en pista;
- ni el perseguidor ni el rival están en vuelta de entrada o de salida de boxes;
- ni el perseguidor ni el rival pararon en las últimas `recent_stop_laps` vueltas;
- el perseguidor completó al menos la vuelta `min_lap` (guarda configurable contra el
  comienzo de la carrera, donde el intervalo corto lo explica la largada);
- al perseguidor le quedan al menos `min_vueltas_restantes` vueltas (si se conoce el total de
  la carrera, de `circuits.toml`; sin ese dato, la guarda no se aplica). Guarda empírica,
  calibrada con el percentil 10 de vueltas restantes en las paradas reales bajo bandera verde
  del corpus de H2 t2 (docs/lecturas.md), no con la tasa de éxito del undercut.

Condiciones que sí dependen de los umbrales de readings.toml (`max_gap_s` con evidencia desde
H2 t2; `min_tyre_age_laps` sin poder testearse con ese corpus): pista en verde, `interval_s` de
hasta `max_gap_s` y neumático del perseguidor con `min_tyre_age_laps` vueltas o más.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apexpulse.model import Event, LapCompleted, StintStarted, TrackStatus
from apexpulse.readings.config import Messages, UndercutConfig
from apexpulse.readings.format import num
from apexpulse.readings.model import Evidence, Reading

if TYPE_CHECKING:
    from apexpulse.readings.engine import Context
    from apexpulse.readings.stops import StopTracker
    from apexpulse.replay.state import RaceState


@dataclass(frozen=True)
class Evaluation:
    """Resultado de evaluar a un perseguidor al completar una vuelta.

    `guards_ok` es True si pasa las guardas sin calibración; `open` si además cumple las
    condiciones con umbral. Los números quedan para la evidencia y para medir.
    """

    chaser: int
    rival: int
    lap: int
    guards_ok: bool
    open: bool
    gap_s: float | None
    chaser_age: int | None
    rival_age: int | None


class UndercutWindow:
    id = "undercut_window"
    version = 2  # v2: guarda min_lap y evidencia vuelta_perseguidor

    def __init__(self, config: UndercutConfig, messages: Messages) -> None:
        self._config = config
        self._messages = messages
        self._streak: dict[int, tuple[int, int]] = {}  # perseguidor -> (rival, vueltas seguidas)
        self._emitted: set[str] = set()

    def reset(self) -> None:
        self._streak.clear()
        self._emitted.clear()

    def evaluate(self, chaser: int, state: RaceState, tracker: StopTracker) -> Evaluation | None:
        """Evalúa al perseguidor con su última vuelta completada; None si no tiene rival."""
        auto = state.cars.get(chaser)
        if auto is None or auto.position is None or auto.position <= 1 or auto.last_lap is None:
            return None
        rival = next((n for n, a in state.cars.items() if a.position == auto.position - 1), None)
        if rival is None:
            return None
        otro = state.cars[rival]
        lap = auto.last_lap.lap
        cfg = self._config

        intervalo = auto.interval
        gap = None if intervalo is None else intervalo.interval_s
        numerico = (
            intervalo is not None
            and gap is not None
            and intervalo.laps_down is None
            and intervalo.interval_laps is None
            and (otro.interval is None or otro.interval.laps_down is None)
        )
        restantes = None if state.total_laps is None else state.total_laps - lap
        guards_ok = (
            lap >= cfg.min_lap
            and (restantes is None or restantes >= cfg.min_vueltas_restantes)
            and numerico
            and not tracker.in_pit_lap(chaser, state)
            and not tracker.in_pit_lap(rival, state)
            and not tracker.recent_stop(chaser, state, cfg.recent_stop_laps)
            and not tracker.recent_stop(rival, state, cfg.recent_stop_laps)
        )
        edad = _edad(auto.stint, lap)
        edad_rival = None if otro.last_lap is None else _edad(otro.stint, otro.last_lap.lap)
        abierta = (
            guards_ok
            and state.track_status == TrackStatus.GREEN
            and gap is not None
            and gap <= cfg.max_gap_s
            and edad is not None
            and edad >= cfg.min_tyre_age_laps
            and edad_rival is not None  # sin la edad del rival la evidencia queda incompleta
        )
        return Evaluation(chaser, rival, lap, guards_ok, abierta, gap, edad, edad_rival)

    def on_event(self, evento: Event, state: RaceState, ctx: Context) -> list[Reading]:
        if not isinstance(evento, LapCompleted):
            return []
        ev = self.evaluate(evento.driver, state, ctx.stops)
        if ev is None or not ev.open:
            self._streak.pop(evento.driver, None)
            return []
        rival_anterior, n = self._streak.get(evento.driver, (ev.rival, 0))
        n = n + 1 if rival_anterior == ev.rival else 1
        self._streak[evento.driver] = (ev.rival, n)
        auto = state.cars[ev.chaser]
        otro = state.cars[ev.rival]
        assert auto.stint is not None and otro.stint is not None  # la edad exige stint
        key = f"{self.id}:{ev.chaser}:{ev.rival}:{auto.stint.stint}"
        if n < self._config.confirm_laps or key in self._emitted:
            return []
        self._emitted.add(key)
        assert ev.gap_s is not None and ev.chaser_age is not None and ev.rival_age is not None
        m = self._messages
        texto = m.render(
            "undercut_window",
            "abierta",
            perseguidor=state.acronym(ev.chaser),
            rival=state.acronym(ev.rival),
            gap=num(ev.gap_s),
            vueltas=str(n),
            compuesto_p=m.compounds[auto.stint.compound.value],
            edad_p=str(ev.chaser_age),
            compuesto_r=m.compounds[otro.stint.compound.value],
            edad_r=str(ev.rival_age),
        )
        return [
            Reading(
                rule=self.id,
                key=key,
                t=evento.t,
                lap=state.lap,
                drivers=(ev.chaser, ev.rival),
                evidence=(
                    Evidence("gap_s", ev.gap_s, "s"),
                    Evidence("vueltas_seguidas", n, "vueltas"),
                    Evidence("posicion_perseguidor", auto.position or 0),
                    Evidence("vuelta_perseguidor", ev.lap, "vuelta"),
                    Evidence("edad_perseguidor", ev.chaser_age, "vueltas"),
                    Evidence("compuesto_perseguidor", auto.stint.compound.value),
                    Evidence("edad_rival", ev.rival_age, "vueltas"),
                    Evidence("compuesto_rival", otro.stint.compound.value),
                ),
                text=texto,
            )
        ]


def _edad(stint: StintStarted | None, vuelta: int) -> int | None:
    """Vueltas de uso del juego tras completar `vuelta`; None si no hay stint.

    El stint empieza al comenzar su vuelta `lap` con `tyre_age` vueltas de uso: al completar esa
    vuelta suma una más. Un stint que todavía no empezó (`lap` mayor que `vuelta`) cuenta su
    edad inicial.
    """
    if stint is None:
        return None
    return stint.tyre_age + max(vuelta - stint.lap + 1, 0)
