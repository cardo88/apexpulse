"""Motor de lecturas: aplica las reglas a cada evento, en el orden del replay.

El motor es causal y determinístico: una regla usa solo el estado y los eventos recibidos hasta
el evento actual, no mira hacia adelante, no usa el reloj ni azar. Igual que `RaceState`, su
estado es un fold de los eventos: tras un `seek`, el replay lo reinicia y re-pliega en silencio
los eventos salteados (`process` devuelve lecturas que el replay descarta, pero `history` las
conserva). Así el motor produce las mismas lecturas que la reproducción continua y no repite las
anteriores al punto de llegada.

Orden de evaluación: primero el seguimiento de paradas, después las reglas en el orden de
`Engine.rules`; dentro de una regla, por piloto en el orden en que aparecen los eventos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from apexpulse.model import Event
from apexpulse.readings.cheap_stop import CheapStop
from apexpulse.readings.config import Messages, ReadingsConfig, load_config, load_messages
from apexpulse.readings.model import Reading
from apexpulse.readings.stops import RealStop, StopTracker
from apexpulse.readings.undercut import UndercutWindow

if TYPE_CHECKING:
    from apexpulse.replay.state import RaceState


@dataclass(frozen=True)
class Context:
    """Lo que ven las reglas además del estado de la carrera."""

    stops: StopTracker
    new_stops: Sequence[RealStop]  # paradas confirmadas con este evento


class Rule(Protocol):
    id: str
    version: int

    def reset(self) -> None: ...

    def on_event(self, evento: Event, state: RaceState, ctx: Context) -> list[Reading]: ...


class Engine:
    """Reglas más memoria de paradas. Una instancia por reproducción."""

    def __init__(self, config: ReadingsConfig, messages: Messages) -> None:
        self.config = config
        self.tracker = StopTracker(config.stops.confirm_timeout_laps)
        self.rules: list[Rule] = [
            CheapStop(messages),
            UndercutWindow(config.undercut, messages),
        ]
        self._history: list[Reading] = []

    @classmethod
    def default(cls) -> Engine:
        """Motor con la configuración y los textos empaquetados."""
        return cls(load_config(), load_messages())

    @property
    def history(self) -> tuple[Reading, ...]:
        """Todas las lecturas generadas desde el inicio hasta el cursor, también las que un seek
        salteó sin emitirlas."""
        return tuple(self._history)

    def reset(self) -> None:
        self.tracker.reset()
        for regla in self.rules:
            regla.reset()
        self._history.clear()

    def process(self, evento: Event, state: RaceState) -> list[Reading]:
        """Procesa `evento`, que ya está aplicado a `state`; devuelve las lecturas nuevas."""
        ctx = Context(self.tracker, self.tracker.observe(evento, state))
        lecturas: list[Reading] = []
        for regla in self.rules:
            lecturas += regla.on_event(evento, state, ctx)
        self._history += lecturas
        return lecturas
