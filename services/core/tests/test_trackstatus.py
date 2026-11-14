"""Tests de la derivación del estado de pista a partir de mensajes de dirección de carrera."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apexpulse.model import RaceControlMessage, TrackStatus
from apexpulse.sources.trackstatus import derive_track_status

T0 = datetime(2026, 6, 7, 13, 0, tzinfo=UTC)


def _rc(
    segundos: int,
    message: str,
    category: str = "Other",
    flag: str | None = None,
    scope: str | None = None,
    lap: int | None = 10,
) -> RaceControlMessage:
    return RaceControlMessage(
        t=T0 + timedelta(seconds=segundos),
        category=category,
        message=message,
        flag=flag,
        scope=scope,
        lap=lap,
    )


INICIO = _rc(0, "SESSION STARTED", "SessionStatus", lap=1)


def _estados(*mensajes: RaceControlMessage, vueltas: dict[int, int] | None = None) -> list[str]:
    inicios = {v: T0 + timedelta(seconds=s) for v, s in (vueltas or {}).items()}
    return [c.status.value for c in derive_track_status(mensajes, inicios)]


def test_vsc_con_track_clear() -> None:
    assert _estados(
        INICIO,
        _rc(100, "VIRTUAL SAFETY CAR DEPLOYED", "SafetyCar"),
        _rc(200, "VIRTUAL SAFETY CAR ENDING", "SafetyCar"),
        _rc(210, "TRACK CLEAR", "Flag", "CLEAR", "Track"),
    ) == ["GREEN", "VSC", "VSC_ENDING", "GREEN"]


def test_ending_se_cierra_cuando_el_lider_empieza_la_vuelta_siguiente() -> None:
    cambios = derive_track_status(
        [
            INICIO,
            _rc(100, "SAFETY CAR DEPLOYED", "SafetyCar", lap=10),
            _rc(200, "SAFETY CAR IN THIS LAP", "SafetyCar", lap=12),
        ],
        {12: T0 + timedelta(seconds=150), 13: T0 + timedelta(seconds=260)},
    )
    assert [c.status for c in cambios][-1] == TrackStatus.GREEN
    assert cambios[-1].t == T0 + timedelta(seconds=260)
    assert cambios[-1].cause == "el líder empieza la vuelta 13"


def test_track_clear_durante_sc_no_lo_termina() -> None:
    assert _estados(
        INICIO,
        _rc(100, "SAFETY CAR DEPLOYED", "SafetyCar"),
        _rc(150, "TRACK CLEAR", "Flag", "CLEAR", "Track"),
    ) == ["GREEN", "SC"]


def test_roja_termina_solo_con_session_started() -> None:
    assert _estados(
        INICIO,
        _rc(100, "RED FLAG - RACE SUSPENDED"),
        _rc(200, "TRACK CLEAR", "Flag", "CLEAR", "Track"),
        _rc(300, "SESSION STARTED", "SessionStatus"),
        _rc(400, "CHEQUERED FLAG", "Flag", "CHEQUERED", "Track"),
        _rc(500, "SESSION STARTED", "SessionStatus"),
    ) == ["GREEN", "RED", "GREEN", "FINISHED"]


def test_bandera_verde_previa_a_la_largada_no_cuenta() -> None:
    assert _estados(
        _rc(-3600, "GREEN LIGHT - PIT EXIT OPEN", "Flag", "GREEN", "Track"), INICIO
    ) == ["GREEN"]
