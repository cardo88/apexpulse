"""Reloj inyectable del replay: el del sistema para la consola y uno falso para los tests.

El replay solo mide diferencias de tiempo real con `monotonic()` y espera con `sleep()`. El
reloj falso avanza al dormir, así los tests verifican las esperas exactas sin esperar.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


class Clock(Protocol):
    """Tiempo real visto por el replay: segundos monótonos y una espera."""

    def monotonic(self) -> float:
        """Segundos desde un origen arbitrario; solo valen las diferencias."""
        ...

    def sleep(self, seconds: float) -> None:
        """Espera `seconds` segundos reales."""
        ...


class SystemClock:
    """Reloj del sistema: `time.monotonic` y `time.sleep`."""

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass
class FakeClock:
    """Reloj controlado: `sleep` avanza el tiempo sin esperar y registra cada llamada.

    Es invocable (`clock()` equivale a `clock.monotonic()`) para usarlo también como `clock=` del
    límite de tasa de las fuentes.
    """

    t: float = 1_000_000.0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.t

    def __call__(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds
