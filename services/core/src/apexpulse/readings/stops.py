"""Seguimiento de paradas reales: la memoria que comparten las reglas.

Una pasada por el pit lane (`PitLane`) es una parada real si:

1. `stationary_s` no es nulo: se confirma en el momento, sin esperar el stint; o
2. hay un stint nuevo, en la vuelta de la pasada o en la siguiente, con un juego de neumáticos
   distinto. Si el stint todavía no llegó, la confirmación queda diferida y vence sin emitir si
   el piloto completa la vuelta `pasada + confirm_timeout_laps` sin que llegue.

OpenF1 abre el stint en la vuelta de la pasada (Mónaco) o en la siguiente (São Paulo), y bajo SC
parte un stint por cada pasada aunque el juego no cambie. Por eso la sola existencia de un stint
nuevo no alcanza: hace falta que el juego sea distinto (`juego_distinto`).

Todo es causal: la decisión usa solo eventos ya recibidos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from apexpulse.model import (
    Compound,
    Event,
    LapCompleted,
    PitLane,
    StintStarted,
    TrackStatus,
)

if TYPE_CHECKING:
    from apexpulse.replay.state import RaceState


def juego_distinto(
    *,
    compuesto_anterior: Compound | None,
    edad_anterior: int | None,
    vuelta_anterior: int | None,
    compuesto: Compound,
    edad: int | None,
    vuelta: int,
) -> bool:
    """¿El stint nuevo monta un juego de neumáticos distinto del anterior?

    - Compuesto distinto: sí (un compuesto `UNKNOWN` no permite comparar y se ignora).
    - Mismo compuesto: sí si la edad al empezar es menor que la esperada, que es la edad del
      stint anterior más las vueltas transcurridas. Un juego que sigue puesto llega con la edad
      esperada exacta (por ejemplo, el stint 3 de HAM en Mónaco empieza en la vuelta 60 con 4
      vueltas de uso y el 4 en la 61 con 5).
    - Si falta la edad (de uno de los dos stints), decide solo el cambio de compuesto.
    - Sin stint anterior conocido: sí solo si el juego llega sin uso (edad 0).
    """
    if compuesto_anterior is None or vuelta_anterior is None:
        return edad == 0
    if Compound.UNKNOWN not in (compuesto, compuesto_anterior) and compuesto != compuesto_anterior:
        return True
    if edad is None or edad_anterior is None:
        return False
    return edad < edad_anterior + (vuelta - vuelta_anterior)


def _distinto(anterior: StintStarted | None, nuevo: StintStarted) -> bool:
    if nuevo.stint == 1:
        return False  # el primer stint es el de la grilla, no un cambio
    return juego_distinto(
        compuesto_anterior=None if anterior is None else anterior.compound,
        edad_anterior=None if anterior is None else anterior.tyre_age,
        vuelta_anterior=None if anterior is None else anterior.lap,
        compuesto=nuevo.compound,
        edad=nuevo.tyre_age,
        vuelta=nuevo.lap,
    )


@dataclass(frozen=True)
class RealStop:
    """Parada real confirmada.

    `pass_t` es el instante de la pasada y `confirmed_t` el de la confirmación: iguales si hubo
    detención registrada o si el stint ya había llegado, posterior si la confirmación se difirió.
    `status` es el estado de pista en la pasada. `leader_lap` es la vuelta del líder en la pasada
    y `pit_lap` la del piloto (distintas para un auto doblado).
    """

    driver: int
    pit_lap: int
    pass_t: datetime
    confirmed_t: datetime
    leader_lap: int
    status: TrackStatus
    how: Literal["stationary", "stint"]
    lane_s: float | None
    stationary_s: float | None
    stint: StintStarted | None  # el stint que confirmó la parada, si fue por stint


@dataclass(frozen=True)
class _Pending:
    pass_t: datetime
    pit_lap: int
    leader_lap: int
    status: TrackStatus
    lane_s: float | None


@dataclass
class StopTracker:
    """Memoria de paradas por piloto. `observe` se llama una vez por evento, en orden."""

    confirm_timeout_laps: int
    stints: dict[int, tuple[StintStarted | None, StintStarted]] = field(default_factory=dict)
    pending: dict[int, _Pending] = field(default_factory=dict)
    stops: dict[int, list[RealStop]] = field(default_factory=dict)
    pass_laps: dict[int, set[int]] = field(
        default_factory=dict
    )  # todas las pasadas, con o sin parada
    expired: int = 0  # confirmaciones diferidas que vencieron sin emitir

    def reset(self) -> None:
        self.stints.clear()
        self.pending.clear()
        self.stops.clear()
        self.pass_laps.clear()
        self.expired = 0

    def observe(self, evento: Event, state: RaceState) -> list[RealStop]:
        """Actualiza la memoria con `evento` (ya aplicado a `state`); devuelve paradas nuevas."""
        confirmadas: list[RealStop] = []
        match evento:
            case StintStarted():
                previo = self.stints.get(evento.driver)
                anterior = None if previo is None else previo[1]
                self.stints[evento.driver] = (anterior, evento)
                pendiente = self.pending.get(evento.driver)
                if pendiente is not None:
                    parada = self._resolver(pendiente, evento, anterior)
                    if parada is not None:
                        confirmadas.append(parada)
            case PitLane():
                confirmadas += self._pasada(evento, state)
            case LapCompleted():
                pendiente = self.pending.get(evento.driver)
                if (
                    pendiente is not None
                    and evento.lap >= pendiente.pit_lap + self.confirm_timeout_laps
                ):
                    del self.pending[evento.driver]
                    self.expired += 1
        for parada in confirmadas:
            self.stops.setdefault(parada.driver, []).append(parada)
        return confirmadas

    def _resolver(
        self, pendiente: _Pending, stint: StintStarted, anterior: StintStarted | None
    ) -> RealStop | None:
        """Un stint llega con una confirmación diferida pendiente."""
        driver = stint.driver
        if stint.lap > pendiente.pit_lap + 1:
            del self.pending[driver]  # llegó tarde: no es de esta pasada
            self.expired += 1
            return None
        del self.pending[driver]
        if not _distinto(anterior, stint):
            return None  # el stint se partió, pero el juego es el mismo: no hubo cambio
        return RealStop(
            driver=driver,
            pit_lap=pendiente.pit_lap,
            pass_t=pendiente.pass_t,
            confirmed_t=stint.t,
            leader_lap=pendiente.leader_lap,
            status=pendiente.status,
            how="stint",
            lane_s=pendiente.lane_s,
            stationary_s=None,
            stint=stint,
        )

    def _pasada(self, pit: PitLane, state: RaceState) -> list[RealStop]:
        driver = pit.driver
        self.pass_laps.setdefault(driver, set()).add(pit.lap)
        if driver in self.pending:  # una pasada nueva reemplaza a la que seguía sin confirmar
            del self.pending[driver]
            self.expired += 1
        # El estado ya incluye este evento: la vuelta del líder es la de la pasada, y el estado
        # de pista también (los cambios de estado se ordenan antes que `pit` en el mismo instante).
        status = state.track_status
        if pit.stationary_s is not None:
            return [
                RealStop(
                    driver,
                    pit.lap,
                    pit.t,
                    pit.t,
                    state.lap,
                    status,
                    "stationary",
                    pit.lane_s,
                    pit.stationary_s,
                    None,
                )
            ]
        par = self.stints.get(driver)
        if par is not None and par[1].lap in (pit.lap, pit.lap + 1):
            # El stint llegó antes que la pasada (Mónaco, o su vuelta siguiente): se decide ya.
            nuevo_stint = _distinto(par[0], par[1])
            if nuevo_stint:
                return [
                    RealStop(
                        driver,
                        pit.lap,
                        pit.t,
                        pit.t,
                        state.lap,
                        status,
                        "stint",
                        pit.lane_s,
                        None,
                        par[1],
                    )
                ]
            if par[1].lap == pit.lap + 1:
                return []  # ya no puede llegar otro stint que decida esta pasada
        self.pending[driver] = _Pending(pit.t, pit.lap, state.lap, status, pit.lane_s)
        return []

    # Consultas para las reglas ---------------------------------------------------------------

    def in_pit_lap(self, driver: int, state: RaceState) -> bool:
        """¿La última vuelta completada del piloto fue de entrada o de salida de boxes?

        Incluye la vuelta en curso si el piloto ya pasó por boxes en ella.
        """
        ultima = state.cars[driver].last_lap if driver in state.cars else None
        if ultima is None:
            return False
        pasadas = self.pass_laps.get(driver, set())
        stint = state.cars[driver].stint
        # Un stint que empieza después de la última vuelta completada es un juego recién puesto.
        recien_puesto = stint is not None and stint.lap > ultima.lap
        return ultima.pit_out or ultima.lap in pasadas or ultima.lap + 1 in pasadas or recien_puesto

    def recent_stop(self, driver: int, state: RaceState, laps: int) -> bool:
        """¿Paró de verdad en las últimas `laps` vueltas completadas?"""
        ultima = state.cars[driver].last_lap if driver in state.cars else None
        if ultima is None or laps == 0:
            return False
        return any(p.pit_lap > ultima.lap - laps for p in self.stops.get(driver, []))
