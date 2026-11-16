"""Test de contrato de `escanear_anio` (`sources/openf1_scan.py`) contra OpenF1 simulado.

Cinco sesiones sintéticas: una disponible y seca, una cancelada, una futura (sin histórico
todavía), una sin slug en `circuits.toml` y una con bandera roja real junto a un `CHEQUERED FLAG`
(para dejar explícito que no se confunde con la roja, el motivo de agregar este escaneo).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from apexpulse.sources.openf1_scan import escanear_anio
from apexpulse.sources.ratelimit import RateLimiter

AHORA = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def _sesion(
    key: int, circuito: str, *, inicio: str, fin: str, cancelada: bool = False
) -> dict[str, Any]:
    return {
        "session_key": key,
        "meeting_key": key,
        "year": 2026,
        "session_name": "Race",
        "circuit_short_name": circuito,
        "date_start": inicio,
        "date_end": fin,
        "is_cancelled": cancelada,
    }


SESIONES = [
    _sesion(1, "Catalunya", inicio="2026-06-14T13:00:00Z", fin="2026-06-14T15:00:00Z"),
    _sesion(2, "Sakhir", inicio="2026-04-12T15:00:00Z", fin="2026-04-12T17:00:00Z", cancelada=True),
    _sesion(3, "Las Vegas", inicio="2026-11-22T06:00:00Z", fin="2026-11-22T08:00:00Z"),
    _sesion(4, "Kuala Lumpur", inicio="2026-10-04T07:00:00Z", fin="2026-10-04T09:00:00Z"),
    _sesion(5, "Monza", inicio="2026-09-06T13:00:00Z", fin="2026-09-06T15:00:00Z"),
    # Sesión que no es carrera: no debe aparecer en el resultado.
    {
        **_sesion(9, "Catalunya", inicio="2026-06-13T11:00:00Z", fin="2026-06-13T12:00:00Z"),
        "session_name": "Qualifying",
    },
]

RC_POR_SESION: dict[int, list[dict[str, Any]]] = {
    1: [
        {"date": "2026-06-14T13:00:00Z", "category": "SessionStatus", "message": "SESSION STARTED"},
        {
            "date": "2026-06-14T14:59:00Z",
            "category": "Flag",
            "flag": "CHEQUERED",
            "scope": "Track",
            "message": "CHEQUERED FLAG",
        },
    ],
    4: [
        {"date": "2026-10-04T07:00:00Z", "category": "SessionStatus", "message": "SESSION STARTED"},
    ],
    5: [
        {"date": "2026-09-06T13:00:00Z", "category": "SessionStatus", "message": "SESSION STARTED"},
        {
            "date": "2026-09-06T14:00:00Z",
            "category": "Other",
            "message": "RED FLAG - RACE SUSPENDED",
        },
        {"date": "2026-09-06T14:30:00Z", "category": "SessionStatus", "message": "SESSION STARTED"},
        {
            "date": "2026-09-06T14:59:00Z",
            "category": "Flag",
            "flag": "CHEQUERED",
            "scope": "Track",
            "message": "CHEQUERED FLAG",
        },
    ],
}

WEATHER_POR_SESION: dict[int, list[dict[str, Any]]] = {
    1: [
        {
            "date": "2026-06-14T13:30:00Z",
            "air_temperature": 25.0,
            "track_temperature": 35.0,
            "rainfall": 0,
        }
    ],
    4: [
        {
            "date": "2026-10-04T07:30:00Z",
            "air_temperature": 28.0,
            "track_temperature": 38.0,
            "rainfall": 1,
        }
    ],
    5: [
        {
            "date": "2026-09-06T13:30:00Z",
            "air_temperature": 22.0,
            "track_temperature": 30.0,
            "rainfall": 0,
        }
    ],
}

PIT_POR_SESION: dict[int, list[dict[str, Any]]] = {
    1: [
        # Dos paradas con detención en verde, antes del CHEQUERED FLAG.
        {
            "date": "2026-06-14T13:20:00Z",
            "driver_number": 1,
            "lap_number": 10,
            "stop_duration": 2.5,
        },
        {
            "date": "2026-06-14T13:40:00Z",
            "driver_number": 2,
            "lap_number": 20,
            "stop_duration": 2.6,
        },
        # Pasada sin detención (cambio de alerón, por ejemplo): no cuenta.
        {
            "date": "2026-06-14T13:45:00Z",
            "driver_number": 3,
            "lap_number": 21,
            "stop_duration": None,
        },
    ],
    4: [
        {"date": "2026-10-04T07:40:00Z", "driver_number": 1, "lap_number": 5, "stop_duration": 3.0},
    ],
    5: [
        # Bajo bandera roja: no debe contar como parada en verde.
        {
            "date": "2026-09-06T14:10:00Z",
            "driver_number": 1,
            "lap_number": 15,
            "stop_duration": 4.0,
        },
        # Después de reanudar, antes del CHEQUERED: en verde.
        {
            "date": "2026-09-06T14:40:00Z",
            "driver_number": 2,
            "lap_number": 30,
            "stop_duration": 2.1,
        },
    ],
}


def _handler(request: httpx.Request) -> httpx.Response:
    endpoint = request.url.path.rsplit("/", 1)[-1]
    if endpoint == "sessions":
        return httpx.Response(200, json=SESIONES)
    session_key = int(request.url.params["session_key"])
    tabla = {"weather": WEATHER_POR_SESION, "race_control": RC_POR_SESION, "pit": PIT_POR_SESION}
    return httpx.Response(200, json=tabla[endpoint].get(session_key, []))


@pytest.fixture
def cliente() -> httpx.Client:
    return httpx.Client(
        base_url="https://api.openf1.org/v1", transport=httpx.MockTransport(_handler)
    )


def _escanear(tmp_path: Path, cliente: httpx.Client, **kwargs: Any) -> list[Any]:
    return escanear_anio(
        2026,
        raw_root=tmp_path / "raw",
        fixtures_root=tmp_path / "fixtures",
        client=cliente,
        limiter=RateLimiter(((1.0, 100),), sleep=lambda _: None),
        now=lambda: AHORA,
        **kwargs,
    )


def test_filtra_qualifying_y_mantiene_el_orden_por_fecha(
    tmp_path: Path, cliente: httpx.Client
) -> None:
    resultados = _escanear(tmp_path, cliente)
    assert [r.session_key for r in resultados] == [2, 1, 5, 4, 3]


def test_sesion_cancelada_no_tiene_metricas(tmp_path: Path, cliente: httpx.Client) -> None:
    (cancelada,) = [r for r in _escanear(tmp_path, cliente) if r.session_key == 2]
    assert cancelada.disponible is False
    assert cancelada.lluvia is None
    assert cancelada.slug == "bahrein"


def test_sesion_futura_no_tiene_metricas(tmp_path: Path, cliente: httpx.Client) -> None:
    (futura,) = [r for r in _escanear(tmp_path, cliente) if r.session_key == 3]
    assert futura.disponible is False
    assert futura.slug == "las-vegas"


def test_circuito_sin_slug_avisa_pero_calcula_metricas(
    tmp_path: Path, cliente: httpx.Client
) -> None:
    (kl,) = [r for r in _escanear(tmp_path, cliente) if r.session_key == 4]
    assert kl.slug is None
    assert kl.disponible is True
    assert kl.lluvia is True
    assert kl.ya_usada is False
    assert "circuito sin slug en circuits.toml: Kuala Lumpur" in kl.avisos


def test_paradas_con_detencion_y_en_verde(tmp_path: Path, cliente: httpx.Client) -> None:
    (catalunya,) = [r for r in _escanear(tmp_path, cliente) if r.session_key == 1]
    assert catalunya.paradas_con_detencion == 2  # la tercera pasada no tiene stop_duration
    assert catalunya.paradas_en_verde == 2
    assert catalunya.lluvia is False
    assert catalunya.bandera_roja is False  # el CHEQUERED FLAG no cuenta como roja


def test_bandera_roja_real_excluye_paradas_en_verde_durante_la_suspension(
    tmp_path: Path, cliente: httpx.Client
) -> None:
    (monza,) = [r for r in _escanear(tmp_path, cliente) if r.session_key == 5]
    assert monza.bandera_roja is True
    assert monza.paradas_con_detencion == 2
    assert monza.paradas_en_verde == 1  # la de la v15, bajo bandera roja, no cuenta
    assert monza.periodos_sc_vsc == 0


def test_ya_usada_si_existe_el_fixture(tmp_path: Path, cliente: httpx.Client) -> None:
    (tmp_path / "fixtures" / "2026-barcelona-r").mkdir(parents=True)
    (catalunya,) = [r for r in _escanear(tmp_path, cliente) if r.session_key == 1]
    assert catalunya.ya_usada is True


def test_excluir_por_slug_saltea_la_sesion(tmp_path: Path, cliente: httpx.Client) -> None:
    resultados = _escanear(tmp_path, cliente, excluir=frozenset({"barcelona"}))
    assert 1 not in [r.session_key for r in resultados]


def test_segunda_corrida_no_pide_de_nuevo_lo_cacheado(
    tmp_path: Path, cliente: httpx.Client
) -> None:
    """La caché de `_escaneo/` evita repetir weather/race_control/pit en una segunda corrida."""
    _escanear(tmp_path, cliente)

    def solo_sessions(request: httpx.Request) -> httpx.Response:
        if request.url.path.rsplit("/", 1)[-1] == "sessions":
            return httpx.Response(200, json=SESIONES)
        raise AssertionError("no debería pedir de nuevo un endpoint ya cacheado")

    cliente_sin_datos = httpx.Client(
        base_url="https://api.openf1.org/v1", transport=httpx.MockTransport(solo_sessions)
    )
    resultados = _escanear(tmp_path, cliente_sin_datos)
    assert len(resultados) == 5
