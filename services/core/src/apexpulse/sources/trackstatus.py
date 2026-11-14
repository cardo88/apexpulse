"""Deriva el estado de pista (SC, VSC, rojo) de los mensajes de dirección de carrera.

Lo usan las fuentes que no publican el estado de pista como dato propio (OpenF1). Transiciones,
verificadas con 2026-monaco-r (SC en las vueltas 60 y 66, bandera roja en la 68):

| Mensaje                                         | Estado nuevo |
|-------------------------------------------------|--------------|
| SessionStatus SESSION STARTED o SESSION RESUMED | GREEN        |
| SafetyCar ... SAFETY CAR DEPLOYED               | SC           |
| SafetyCar ... SAFETY CAR IN THIS LAP            | SC_ENDING    |
| SafetyCar ... VIRTUAL SAFETY CAR DEPLOYED       | VSC          |
| SafetyCar ... VIRTUAL SAFETY CAR ENDING         | VSC_ENDING   |
| Bandera RED, RED FLAG ... o SESSION ABORTED     | RED          |
| Bandera CHEQUERED o SESSION FINISHED            | FINISHED     |
| TRACK CLEAR o bandera GREEN de pista, en ENDING | GREEN        |

Un estado `*_ENDING` también pasa a GREEN cuando el líder empieza la vuelta siguiente a la del
mensaje, si eso ocurre antes que un TRACK CLEAR. Un TRACK CLEAR durante SC, VSC o rojo no
cambia el estado: el rojo termina solo con SESSION STARTED.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

from apexpulse.model.events import RaceControlMessage, TrackStatus, TrackStatusChanged

_ENDING = frozenset({TrackStatus.SC_ENDING, TrackStatus.VSC_ENDING})


def _transicion(rc: RaceControlMessage, actual: TrackStatus | None) -> TrackStatus | None:
    texto = rc.message.upper()
    categoria = rc.category.upper()
    bandera = (rc.flag or "").upper()
    if categoria == "SESSIONSTATUS":
        if "STARTED" in texto or "RESUMED" in texto:
            return TrackStatus.GREEN
        if "ABORTED" in texto or "SUSPENDED" in texto:
            return TrackStatus.RED
        if "FINISHED" in texto or "ENDED" in texto or "FINALISED" in texto:
            return TrackStatus.FINISHED
        return None
    if bandera == "RED" or texto.startswith("RED FLAG"):
        return TrackStatus.RED
    if bandera == "CHEQUERED":
        return TrackStatus.FINISHED
    if categoria == "SAFETYCAR":
        if "VIRTUAL SAFETY CAR DEPLOYED" in texto:
            return TrackStatus.VSC
        if "VIRTUAL SAFETY CAR ENDING" in texto:
            return TrackStatus.VSC_ENDING
        if "SAFETY CAR DEPLOYED" in texto:
            return TrackStatus.SC
        if "IN THIS LAP" in texto:
            return TrackStatus.SC_ENDING
        return None
    if actual in _ENDING and (rc.scope or "").upper() == "TRACK" and bandera in ("GREEN", "CLEAR"):
        return TrackStatus.GREEN
    return None


def derive_track_status(
    messages: Iterable[RaceControlMessage], leader_lap_starts: Mapping[int, datetime]
) -> list[TrackStatusChanged]:
    """Devuelve los cambios de estado en orden.

    `leader_lap_starts` mapea cada vuelta al primer instante en que algún auto la empieza, que
    es cuando el líder cruza la línea.
    """
    cambios: list[TrackStatusChanged] = []
    actual: TrackStatus | None = None
    fin_por_vuelta: int | None = None  # vuelta cuyo inicio cierra el *_ENDING vigente

    def emitir(t: datetime, estado: TrackStatus, vuelta: int | None, causa: str) -> None:
        nonlocal actual, fin_por_vuelta
        if estado == actual or actual == TrackStatus.FINISHED:
            return
        actual = estado
        fin_por_vuelta = None
        cambios.append(TrackStatusChanged(t=t, status=estado, lap=vuelta, cause=causa))

    def cerrar_ending_hasta(t: datetime | None) -> None:
        if actual not in _ENDING or fin_por_vuelta is None:
            return
        inicio = leader_lap_starts.get(fin_por_vuelta)
        if inicio is not None and (t is None or inicio <= t):
            emitir(
                inicio,
                TrackStatus.GREEN,
                fin_por_vuelta,
                f"el líder empieza la vuelta {fin_por_vuelta}",
            )

    for rc in sorted(messages, key=lambda m: m.t):
        cerrar_ending_hasta(rc.t)
        nuevo = _transicion(rc, actual)
        if nuevo is None:
            continue
        if actual is None and nuevo == TrackStatus.FINISHED:
            continue  # mensajes de una sesión anterior en el mismo feed
        emitir(rc.t, nuevo, rc.lap, rc.message)
        if nuevo in _ENDING and rc.lap is not None and actual == nuevo:
            fin_por_vuelta = rc.lap + 1
    cerrar_ending_hasta(None)
    return cambios
