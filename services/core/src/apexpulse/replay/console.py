"""Salida del replay por consola: una línea por hecho relevante, con hora UTC y vuelta del líder.

Por defecto se imprimen un marcador por vuelta, los cambios de estado de pista, los mensajes de
dirección de carrera (sin traducir y sin las banderas azules) y las paradas con detención. Con
`verbose` sale cada evento.
"""

from __future__ import annotations

from collections.abc import Iterable

from apexpulse.model import (
    DriverInfo,
    IntervalUpdated,
    LapCompleted,
    PitLane,
    PositionChanged,
    RaceControlMessage,
    StintStarted,
    TrackStatusChanged,
    WeatherSample,
)
from apexpulse.replay.player import Step
from apexpulse.replay.state import RaceState


def _num(valor: float, decimales: int = 1) -> str:
    return f"{valor:.{decimales}f}".replace(".", ",")


def _tiempo_vuelta(segundos: float) -> str:
    minutos, resto = divmod(segundos, 60)
    return f"{int(minutos)}:{resto:06.3f}".replace(".", ",")


class ConsolePrinter:
    """Convierte lotes del replay en líneas de texto."""

    def __init__(self, state: RaceState, *, verbose: bool = False) -> None:
        self._state = state
        self._verbose = verbose
        self._ultima_vuelta: int | None = None

    def lines(self, lote: Iterable[Step]) -> list[str]:
        salida: list[str] = []
        for paso in lote:
            if paso.lap != self._ultima_vuelta:
                self._ultima_vuelta = paso.lap
                lider = self._state.acronym(paso.leader) if paso.leader is not None else "---"
                salida.append(f"── Vuelta {paso.lap} · lidera {lider}")
            texto = self._describir(paso)
            if texto is not None:
                salida.append(f"{paso.event.t:%H:%M:%S}  v{paso.lap:<3} {texto}")
        return salida

    def _describir(self, paso: Step) -> str | None:
        e = paso.event
        cod = self._state.acronym
        match e:
            case TrackStatusChanged():
                return f"PISTA      {e.status.value} ({e.cause})"
            case RaceControlMessage():
                if e.flag == "BLUE" and not self._verbose:
                    return None
                return f"DIRECCIÓN  {e.message}"
            case PitLane() if e.stationary_s is not None:
                carril = "" if e.lane_s is None else f" · {_num(e.lane_s)} s en pit lane"
                return f"PARADA     {cod(e.driver)} {_num(e.stationary_s)} s detenido{carril}"
        if not self._verbose:
            return None
        match e:
            case PitLane():
                carril = "" if e.lane_s is None else f" · {_num(e.lane_s)} s"
                return f"PIT LANE   {cod(e.driver)} sin detención{carril}"
            case DriverInfo():
                equipo = "" if e.team is None else f" ({e.team})"
                return f"PILOTO     {e.driver:>2} {e.acronym} {e.name}{equipo}"
            case LapCompleted():
                tiempo = "sin tiempo" if e.lap_time_s is None else _tiempo_vuelta(e.lap_time_s)
                return f"VUELTA     {cod(e.driver)} v{e.lap} {tiempo}"
            case StintStarted():
                return (
                    f"STINT      {cod(e.driver)} stint {e.stint} {e.compound.value}"
                    f" ({e.tyre_age} vueltas de uso)"
                )
            case PositionChanged():
                return f"POSICIÓN   {cod(e.driver)} P{e.position}"
            case IntervalUpdated():
                if e.laps_down is not None:
                    gap = f"{e.laps_down} vuelta(s) abajo"
                elif e.gap_s is not None:
                    gap = f"+{_num(e.gap_s, 3)} s al líder"
                else:
                    gap = "sin gap"
                return f"INTERVALO  {cod(e.driver)} {gap}"
            case WeatherSample():
                lluvia = "sí" if e.rain else "no"
                return (
                    f"CLIMA      aire {_num(e.air_c)} °C · pista {_num(e.track_c)} °C"
                    f" · lluvia {lluvia}"
                )
        return None
