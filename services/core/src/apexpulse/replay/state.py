"""Estado acumulado de la carrera: un fold puro de los eventos canónicos en orden.

`RaceState.apply` es la única forma de cambiarlo, así que el estado después de un seek es el
mismo que el de reproducir la sesión hasta ese instante.

Convención de vuelta: la vuelta N es la vuelta en curso del líder y empieza cuando el primer auto
completa la N-1. Se calcula como el máximo de vueltas completadas por cualquier auto más uno, y
queda fija en la vuelta de la bandera a cuadros. Es la misma que usa la FIA en el `lap` de los
mensajes de dirección de carrera. El líder que se nombra es el piloto en posición 1, que puede no
ser el que más vueltas completó en ese instante (por ejemplo, justo después de una parada).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from apexpulse.model import (
    DriverInfo,
    Event,
    IntervalUpdated,
    LapCompleted,
    PitLane,
    PositionChanged,
    StintStarted,
    TrackStatus,
    TrackStatusChanged,
    WeatherSample,
)


@dataclass
class CarState:
    """Lo último que se sabe de un auto."""

    position: int | None = None
    last_lap: LapCompleted | None = None
    stint: StintStarted | None = None
    interval: IntervalUpdated | None = None
    stops: int = 0  # paradas con detención registrada (`stationary_s` no nulo)
    lane_passes: int = 0  # pasadas por el pit lane sin detención registrada


@dataclass
class RaceState:
    """Foto de la carrera después de aplicar una secuencia de eventos."""

    drivers: dict[int, DriverInfo] = field(default_factory=dict)
    cars: dict[int, CarState] = field(default_factory=dict)
    track_status: TrackStatus = TrackStatus.GREEN
    laps_completed: int = 0  # máximo de vueltas completadas por cualquier auto
    final_lap: int | None = None  # vuelta en curso cuando salió la bandera a cuadros
    weather: WeatherSample | None = None
    last_t: datetime | None = None
    events_applied: int = 0

    @property
    def lap(self) -> int:
        """Vuelta en curso del líder (ver la convención en el docstring del módulo)."""
        if self.final_lap is not None:
            return self.final_lap
        return self.laps_completed + 1

    @property
    def leader(self) -> int | None:
        """Número del piloto en posición 1, o None si todavía no hay posiciones."""
        for numero, auto in self.cars.items():
            if auto.position == 1:
                return numero
        return None

    def acronym(self, driver: int | None) -> str:
        """Código de 3 letras del piloto; el número si la sesión no trae el evento `driver`."""
        if driver is None:
            return "---"
        info = self.drivers.get(driver)
        return info.acronym if info is not None else f"#{driver}"

    def car(self, driver: int) -> CarState:
        return self.cars.setdefault(driver, CarState())

    def apply(self, evento: Event) -> None:
        """Aplica un evento. Los eventos tienen que llegar en el orden de `sort_key`."""
        self.last_t = evento.t
        self.events_applied += 1
        match evento:
            case DriverInfo():
                self.drivers[evento.driver] = evento
                self.car(evento.driver)
            case LapCompleted():
                self.car(evento.driver).last_lap = evento
                self.laps_completed = max(self.laps_completed, evento.lap)
            case StintStarted():
                self.car(evento.driver).stint = evento
            case PitLane():
                auto = self.car(evento.driver)
                if evento.stationary_s is None:
                    auto.lane_passes += 1
                else:
                    auto.stops += 1
            case PositionChanged():
                # Una posición nueva desplaza al que la tenía; el desplazado recibe la suya en
                # su propio evento, normalmente con el mismo instante.
                for otro in self.cars.values():
                    if otro.position == evento.position:
                        otro.position = None
                self.car(evento.driver).position = evento.position
            case IntervalUpdated():
                self.car(evento.driver).interval = evento
            case TrackStatusChanged():
                if evento.status is TrackStatus.FINISHED and self.final_lap is None:
                    self.final_lap = self.lap
                self.track_status = evento.status
            case WeatherSample():
                self.weather = evento
            case _:  # race_control: no cambia la foto; el estado de pista llega derivado
                pass
