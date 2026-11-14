"""Test de contrato del adaptador OpenF1 contra respuestas grabadas de 2026-sao-paulo-r.

Las respuestas viven en fixtures/sessions/2026-sao-paulo-r/openf1/ (recortadas de la API real
el 2026-11-14). Ningún test usa la red.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from apexpulse.session_id import SessionId
from apexpulse.sources import OpenF1Adapter, SchemaError, SourceError
from apexpulse.sources.openf1 import ENDPOINTS, RATE_LIMITS
from apexpulse.sources.ratelimit import RateLimiter
from apexpulse.sources.rawstore import read_jsonl_zst
from conftest import FakeClock, FakeOpenF1

SESION = SessionId.parse("2026-sao-paulo-r")
AHORA = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)


def _adapter(openf1: FakeOpenF1, clock: FakeClock, **kwargs: Any) -> OpenF1Adapter:
    limiter = RateLimiter(RATE_LIMITS, clock=clock, sleep=clock.sleep)
    return OpenF1Adapter(openf1.client(), limiter, sleep=clock.sleep, now=lambda: AHORA, **kwargs)


def test_descarga_completa(tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock) -> None:
    report = _adapter(openf1, clock).fetch(SESION, tmp_path)

    assert report.source_session_key == 11412
    assert report.requests == 1 + len(ENDPOINTS)
    assert not report.from_cache
    assert openf1.paths() == ["sessions", *ENDPOINTS]
    assert openf1.requests[0].url.params["year"] == "2026"
    assert all(r.url.params["session_key"] == "11412" for r in openf1.requests[1:])

    destino = tmp_path / "2026" / "2026-sao-paulo-r" / "openf1"
    assert report.dest == destino
    for endpoint in ENDPOINTS:
        guardado = list(read_jsonl_zst(destino / f"{endpoint}.jsonl.zst"))
        assert guardado == openf1.endpoint_json(endpoint), endpoint
        assert report.rows[endpoint] == len(guardado)

    manifiesto = json.loads((destino / "manifest.json").read_text(encoding="utf-8"))
    assert manifiesto["session"] == "2026-sao-paulo-r"
    assert manifiesto["openf1_session"]["circuit_short_name"] == "Interlagos"
    assert manifiesto["endpoints"]["laps"] == {"file": "laps.jsonl.zst", "rows": 4}
    assert (tmp_path / "2026" / "_openf1" / "sessions.jsonl.zst").exists()
    assert report.warnings == []


def test_segunda_descarga_usa_la_cache(
    tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock
) -> None:
    primera = _adapter(openf1, clock).fetch(SESION, tmp_path)
    openf1.requests.clear()
    segunda = _adapter(openf1, clock).fetch(SESION, tmp_path)
    assert openf1.requests == []
    assert segunda.from_cache and segunda.requests == 0
    assert segunda.rows == primera.rows
    assert segunda.source_session_key == 11412


def test_force_vuelve_a_bajar(tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock) -> None:
    _adapter(openf1, clock).fetch(SESION, tmp_path)
    openf1.requests.clear()
    _adapter(openf1, clock).fetch(SESION, tmp_path, force=True)
    assert openf1.paths() == ["sessions", *ENDPOINTS]


def test_otra_sesion_del_mismo_anio_reutiliza_sessions(
    tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock
) -> None:
    # La carrera de Baréin 2026 figura con is_cancelled=true en la respuesta grabada.
    _adapter(openf1, clock).fetch(SESION, tmp_path)
    openf1.requests.clear()
    with pytest.raises(SourceError, match="2026-bahrein-r: la sesión figura como cancelada"):
        _adapter(openf1, clock).fetch(SessionId.parse("2026-bahrein-r"), tmp_path)
    assert openf1.requests == []


def test_descarga_incompleta_se_rehace(
    tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock
) -> None:
    openf1.overrides["weather"] = [httpx.Response(400, text="bad request")]
    with pytest.raises(SourceError, match="weather respondió 400"):
        _adapter(openf1, clock).fetch(SESION, tmp_path)
    destino = tmp_path / "2026" / "2026-sao-paulo-r" / "openf1"
    assert not (destino / "manifest.json").exists()
    openf1.requests.clear()
    assert not _adapter(openf1, clock).fetch(SESION, tmp_path).from_cache
    assert "laps" in openf1.paths()


def test_respeta_el_limite_de_tasa(tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock) -> None:
    _adapter(openf1, clock).fetch(SESION, tmp_path)
    tiempos = openf1.times
    for i in range(len(tiempos)):
        en_un_segundo = [t for t in tiempos if tiempos[i] <= t < tiempos[i] + 1.0]
        assert len(en_un_segundo) <= 3
    assert clock.sleeps  # 8 requests: tuvo que esperar al menos una vez


def test_429_con_retry_after(tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock) -> None:
    openf1.overrides["laps"] = [
        httpx.Response(429, headers={"Retry-After": "7"}, json={"detail": "rate limit"}),
    ]
    report = _adapter(openf1, clock).fetch(SESION, tmp_path)
    assert openf1.paths().count("laps") == 2
    assert 7.0 in clock.sleeps
    assert report.requests == 2 + len(ENDPOINTS)


def test_backoff_exponencial_y_falla_tras_reintentos(
    tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock
) -> None:
    openf1.overrides["laps"] = [httpx.Response(503) for _ in range(4)]
    with pytest.raises(SourceError, match="HTTP 503 tras 4 intentos"):
        _adapter(openf1, clock, max_retries=3).fetch(SESION, tmp_path)
    esperas_backoff = [s for s in clock.sleeps if s in (1.0, 2.0, 4.0)]
    assert esperas_backoff[-3:] == [1.0, 2.0, 4.0]


def test_error_de_red_se_reintenta(tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock) -> None:
    original = openf1.handler
    fallas = {"n": 0}

    def con_corte(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pit") and fallas["n"] == 0:
            fallas["n"] += 1
            raise httpx.ConnectError("conexión reiniciada", request=request)
        return original(request)

    openf1.handler = con_corte  # type: ignore[method-assign]
    report = _adapter(openf1, clock).fetch(SESION, tmp_path)
    assert report.rows["pit"] == 3


def test_404_sin_resultados_es_lista_vacia(
    tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock
) -> None:
    openf1.overrides["pit"] = [httpx.Response(404, json={"detail": "No results found."})]
    report = _adapter(openf1, clock).fetch(SESION, tmp_path)
    assert report.rows["pit"] == 0
    assert "pit: OpenF1 no devolvió registros" in report.warnings


def test_campo_desconocido_avisa_con_muestra(
    tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock
) -> None:
    def agregar_campo(datos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**r, "tyre_temperature": 98.5} for r in datos]

    openf1.edits["stints"] = agregar_campo
    report = _adapter(openf1, clock).fetch(SESION, tmp_path)
    assert report.warnings == ["stints: campos desconocidos: tyre_temperature=98.5"]


def test_campo_obligatorio_faltante_falla(
    tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock
) -> None:
    def quitar_campo(datos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{k: v for k, v in r.items() if k != "gap_to_leader"} for r in datos]

    openf1.edits["intervals"] = quitar_campo
    with pytest.raises(SchemaError, match="intervals: el registro 0 no tiene gap_to_leader"):
        _adapter(openf1, clock).fetch(SESION, tmp_path)


def test_registro_de_otra_sesion_falla(
    tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock
) -> None:
    openf1.edits["position"] = lambda datos: [{**datos[0], "session_key": 9999}]
    with pytest.raises(SchemaError, match="es de la sesión 9999"):
        _adapter(openf1, clock).fetch(SESION, tmp_path)


def test_respuesta_que_no_es_lista(tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock) -> None:
    openf1.overrides["laps"] = [httpx.Response(200, json={"detail": "algo"})]
    with pytest.raises(SchemaError, match="lista de objetos"):
        _adapter(openf1, clock).fetch(SESION, tmp_path)


def test_sesion_sin_terminar(tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock) -> None:
    limiter = RateLimiter(RATE_LIMITS, clock=clock, sleep=clock.sleep)
    durante = datetime(2026, 11, 8, 18, 0, tzinfo=UTC)
    adapter = OpenF1Adapter(openf1.client(), limiter, sleep=clock.sleep, now=lambda: durante)
    with pytest.raises(SourceError, match="histórico de OpenF1 queda disponible desde"):
        adapter.fetch(SESION, tmp_path)
    assert openf1.paths() == ["sessions"]


def test_sesion_cancelada(tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock) -> None:
    def cancelar(datos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**s, "is_cancelled": s["session_key"] == 11412} for s in datos]

    openf1.edits["sessions"] = cancelar
    with pytest.raises(SourceError, match="cancelada"):
        _adapter(openf1, clock).fetch(SESION, tmp_path)


def test_sesion_inexistente_lista_circuitos(
    tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock
) -> None:
    with pytest.raises(SourceError, match=r"Circuitos de OpenF1 en 2026: Interlagos, Sakhir"):
        _adapter(openf1, clock).fetch(SessionId.parse("2026-sao-paulo-s"), tmp_path)


def test_sesion_nueva_en_el_calendario_refresca_sessions(
    tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock
) -> None:
    def sin_carrera(datos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [s for s in datos if s["session_key"] != 11412]

    openf1.edits["sessions"] = sin_carrera
    with pytest.raises(SourceError):
        _adapter(openf1, clock).fetch(SESION, tmp_path)
    del openf1.edits["sessions"]
    openf1.requests.clear()
    report = _adapter(openf1, clock).fetch(SESION, tmp_path)
    assert openf1.paths()[0] == "sessions"
    assert report.source_session_key == 11412
