"""Regla `cheap_stop`: parada real bajo Safety Car o VSC.

Condición: una parada real (ver `stops.py`) cuya pasada por el pit lane ocurrió con el estado de
pista en SC, SC_ENDING o VSC. Con bandera roja no dispara: el cambio de neumáticos es libre y la
parada no es comparable.

`VSC_ENDING` no cuenta, a diferencia de `SC_ENDING` (ambos son `NEUTRALIZED` en el modelo, que
describe el estado físico de la pista, no esta regla). Bajo Safety Car los autos siguen agrupados
detrás del auto de seguridad hasta que entra a boxes; bajo VSC el pelotón ya acelera a ritmo de
carrera antes de que el estado pase a verde, así que una pasada en `VSC_ENDING` no tiene la misma
ventaja comparable. Decisión del autor (docs/lecturas.md); el caso de borde de Australia v34
(BOR, antes la única lectura de ese período) pasa a ser negativo.

La evidencia es solo lo observado. El texto no afirma cuánto tiempo se ahorra: eso requiere el
ritmo del pelotón y la geometría del pit lane de cada circuito, que el modelo no tiene.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apexpulse.model import Event, TrackStatus
from apexpulse.readings.config import Messages
from apexpulse.readings.format import num
from apexpulse.readings.model import Evidence, Reading
from apexpulse.readings.stops import RealStop

if TYPE_CHECKING:
    from apexpulse.readings.engine import Context
    from apexpulse.replay.state import RaceState

_CUENTA_COMO_NEUTRALIZACION = frozenset({TrackStatus.SC, TrackStatus.SC_ENDING, TrackStatus.VSC})


class CheapStop:
    id = "cheap_stop"
    version = 1

    def __init__(self, messages: Messages) -> None:
        self._messages = messages

    def reset(self) -> None:
        """Sin memoria propia: la de las paradas vive en el `StopTracker`."""

    def on_event(self, evento: Event, state: RaceState, ctx: Context) -> list[Reading]:
        return [
            self._lectura(parada, evento, state)
            for parada in ctx.new_stops
            if parada.status in _CUENTA_COMO_NEUTRALIZACION
        ]

    def _lectura(self, parada: RealStop, evento: Event, state: RaceState) -> Reading:
        m = self._messages
        carril = "" if parada.lane_s is None else m.fragment("carril", lane_s=num(parada.lane_s))
        comunes = {
            "piloto": state.acronym(parada.driver),
            "estado": m.states[parada.status.value],
            "vuelta": str(parada.leader_lap),
            "carril": carril,
        }
        evidencia = [
            Evidence("estado_de_pista", parada.status.value),
            Evidence("vuelta_propia", parada.pit_lap, "vuelta"),
            Evidence("instante_pasada", parada.pass_t.isoformat()),
            Evidence("instante_confirmacion", parada.confirmed_t.isoformat()),
            Evidence("criterio", "detencion" if parada.how == "stationary" else "stint"),
        ]
        if parada.lane_s is not None:
            evidencia.append(Evidence("pit_lane_s", parada.lane_s, "s"))
        if parada.stationary_s is not None:
            evidencia.append(Evidence("detenido_s", parada.stationary_s, "s"))
            texto = m.render("cheap_stop", "detenido", detenido=num(parada.stationary_s), **comunes)
        else:
            stint = parada.stint
            assert stint is not None  # una parada por stint siempre trae el stint
            evidencia += [
                Evidence("compuesto", stint.compound.value),
                Evidence("edad_neumatico", stint.tyre_age, "vueltas"),
            ]
            texto = m.render(
                "cheap_stop",
                "cambio",
                compuesto=m.compounds[stint.compound.value],
                edad=str(stint.tyre_age),
                **comunes,
            )
        return Reading(
            rule=self.id,
            key=f"{self.id}:{parada.driver}:{parada.pit_lap}",
            t=evento.t,
            lap=parada.leader_lap,
            drivers=(parada.driver,),
            evidence=tuple(evidencia),
            text=texto,
        )
