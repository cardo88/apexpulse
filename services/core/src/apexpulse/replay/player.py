"""Reproductor de una sesión canónica con velocidad variable, pausa y seek.

Hay dos tiempos: el real, que da el reloj inyectado, y la posición de sesión, en la escala de `t`.
Se vinculan con un ancla (real0, pos0): `pos = pos0 + (real - real0) * speed`. Pausar, reanudar,
cambiar la velocidad o hacer seek solo mueven el ancla.

El orden de emisión es el guardado en el Parquet, que es el de `sort_key`; el replay no reordena,
solo valida. Los eventos con el mismo instante salen juntos en un lote, sin espera entre ellos.

El núcleo no bloquea (`due_in` y `pop_due`), para que la API de H3 lo maneje desde asyncio;
`run` es el bucle bloqueante que usa la consola.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from apexpulse.model import (
    SCHEMA_VERSION,
    Event,
    LapCompleted,
    SessionMeta,
    read_events,
    read_meta,
    sort_key,
)
from apexpulse.replay.clock import Clock
from apexpulse.replay.state import RaceState

# Margen para comparar posiciones en segundos de sesión (las marcas tienen resolución de 1 µs).
_EPS = 1e-7


class ReplayError(Exception):
    """El archivo canónico no se puede reproducir o el pedido no aplica a la sesión."""


@dataclass(frozen=True)
class Step:
    """Un evento emitido con el contexto en el que ocurrió (antes de aplicarlo al estado)."""

    event: Event
    lap: int  # vuelta en curso del líder
    leader: int | None  # piloto en posición 1


class Replay:
    """Reproduce los eventos de una sesión sobre un reloj inyectable.

    `speed` es el multiplicador (30 = 30 s de sesión por segundo real); None reproduce sin espera.
    `max_gap_s`, si se indica, recorta los huecos: cuando faltan más de `max_gap_s` segundos de
    sesión hasta el próximo lote, la posición salta hasta quedar a `max_gap_s` de él.
    `max_sleep_s` acota cada espera real, para atender pausas o seeks pedidos mientras espera.
    """

    def __init__(
        self,
        meta: SessionMeta,
        events: Sequence[Event],
        clock: Clock,
        *,
        speed: float | None = 1.0,
        max_gap_s: float | None = None,
        max_sleep_s: float = 0.5,
    ) -> None:
        _validar_version(meta)
        _validar_orden(events)
        _validar_velocidad(speed)
        if max_gap_s is not None and max_gap_s <= 0:
            raise ReplayError("max_gap_s tiene que ser mayor que 0")
        self.meta = meta
        self._events = list(events)
        self._offsets = [(e.t - meta.start).total_seconds() for e in self._events]
        self._lap_starts = _inicios_de_vuelta(self._events, meta.start)
        self._clock = clock
        self._speed = speed
        self._max_gap_s = max_gap_s
        self._max_sleep_s = max_sleep_s
        self._paused = False
        self._cursor = 0
        self.state = RaceState()
        self._anchor_real = clock.monotonic()
        self._anchor_pos = 0.0
        self.seek(meta.start)

    @classmethod
    def from_parquet(
        cls,
        path: Path,
        clock: Clock,
        *,
        speed: float | None = 1.0,
        max_gap_s: float | None = None,
    ) -> Replay:
        """Carga data/canonical/<sesion>.parquet."""
        if not path.exists():
            raise ReplayError(f"no existe {path}")
        return cls(read_meta(path), read_events(path), clock, speed=speed, max_gap_s=max_gap_s)

    # Consulta -------------------------------------------------------------------------------

    @property
    def speed(self) -> float | None:
        return self._speed

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def finished(self) -> bool:
        return self._cursor >= len(self._events)

    @property
    def remaining(self) -> int:
        return len(self._events) - self._cursor

    @property
    def position(self) -> datetime:
        """Instante de sesión en el que está el replay."""
        return self.meta.start + timedelta(seconds=self._pos())

    def _pos(self) -> float:
        if self._paused or self._speed is None:
            return self._anchor_pos
        return self._anchor_pos + (self._clock.monotonic() - self._anchor_real) * self._speed

    def _reanclar(self, pos: float) -> None:
        self._anchor_pos = pos
        self._anchor_real = self._clock.monotonic()

    # Control --------------------------------------------------------------------------------

    def pause(self) -> None:
        if not self._paused:
            self._reanclar(self._pos())
            self._paused = True

    def resume(self) -> None:
        if self._paused:
            self._paused = False
            self._reanclar(self._anchor_pos)

    def set_speed(self, speed: float | None) -> None:
        _validar_velocidad(speed)
        pos = self._pos()
        self._speed = speed
        self._reanclar(pos)

    def seek(self, t: datetime) -> None:
        """Lleva el replay a `t`: el estado queda con los eventos anteriores a `t`, sin emitirlos.

        Un `t` anterior al inicio de la sesión se ajusta al inicio. Pausa y velocidad no cambian.
        """
        objetivo = max(0.0, (t - self.meta.start).total_seconds())
        self._ir_a(bisect_left(self._offsets, objetivo - _EPS), objetivo)

    def seek_lap(self, lap: int) -> None:
        """Lleva el replay al comienzo de la vuelta `lap` del líder.

        El estado incluye el lote del cruce que abre la vuelta, así `state.lap == lap`. Para la
        vuelta 1 o menos equivale a `seek(meta.start)`.
        """
        if lap <= 1:
            self.seek(self.meta.start)
            return
        if lap not in self._lap_starts:
            raise ReplayError(f"{self.meta.session}: no hay datos para empezar la vuelta {lap}")
        objetivo = self._lap_starts[lap]
        self._ir_a(bisect_right(self._offsets, objetivo + _EPS), objetivo)

    def _ir_a(self, indice: int, pos: float) -> None:
        if indice < self._cursor:
            self.state = RaceState()
            self._cursor = 0
        for evento in self._events[self._cursor : indice]:
            self.state.apply(evento)
        self._cursor = indice
        self._reanclar(pos)

    # Avance ---------------------------------------------------------------------------------

    def due_in(self) -> float | None:
        """Segundos reales hasta el próximo lote; None si terminó o está en pausa."""
        if self.finished or self._paused:
            return None
        if self._speed is None:
            return 0.0
        proximo = self._offsets[self._cursor]
        pos = self._pos()
        if self._max_gap_s is not None and proximo - pos > self._max_gap_s:
            pos = proximo - self._max_gap_s
            self._reanclar(pos)
        falta = proximo - pos
        # Mismo margen que pop_due: un resto menor no se puede dormir con precisión de float.
        return 0.0 if falta <= _EPS else falta / self._speed

    def pop_due(self) -> list[Step]:
        """Emite el próximo lote si ya venció (lista vacía si no) y lo aplica al estado."""
        if self.finished or self._paused:
            return []
        instante = self._offsets[self._cursor]
        if self._speed is not None and instante > self._pos() + _EPS:
            return []
        lote: list[Step] = []
        while not self.finished and self._offsets[self._cursor] == instante:
            evento = self._events[self._cursor]
            lote.append(Step(evento, self.state.lap, self.state.leader))
            self.state.apply(evento)
            self._cursor += 1
        if self._speed is None:
            self._anchor_pos = instante
        return lote

    def run(self) -> Iterator[list[Step]]:
        """Reproduce hasta el final esperando con el reloj; produce un lote por instante."""
        self._reanclar(self._pos())
        while not self.finished:
            espera = self.due_in()
            if espera is None:
                self._clock.sleep(self._max_sleep_s)
            elif espera > 0:
                self._clock.sleep(min(espera, self._max_sleep_s))
            else:
                lote = self.pop_due()
                if lote:
                    yield lote


def _validar_version(meta: SessionMeta) -> None:
    mayor = SCHEMA_VERSION.split(".")[0]
    if meta.schema_version.split(".")[0] != mayor:
        raise ReplayError(
            f"{meta.session}: esquema canónico {meta.schema_version}, el replay espera {mayor}.x;"
            f" volver a correr make normalize SESSION={meta.session}"
        )


def _validar_orden(events: Sequence[Event]) -> None:
    anterior = None
    for i, evento in enumerate(events):
        clave = sort_key(evento)
        if anterior is not None and clave < anterior:
            raise ReplayError(
                f"eventos fuera de orden en la fila {i} ({evento.kind} {evento.t.isoformat()});"
                " volver a correr make normalize"
            )
        anterior = clave


def _validar_velocidad(speed: float | None) -> None:
    if speed is not None and not speed > 0:
        raise ReplayError(f"la velocidad tiene que ser mayor que 0 (se pidió {speed})")


def _inicios_de_vuelta(events: Sequence[Event], inicio: datetime) -> dict[int, float]:
    """Vuelta N -> segundos desde el inicio en que el primer auto completa la N-1."""
    inicios: dict[int, float] = {}
    for evento in events:
        if isinstance(evento, LapCompleted):
            vuelta = evento.lap + 1
            if vuelta not in inicios:
                inicios[vuelta] = (evento.t - inicio).total_seconds()
    return inicios
