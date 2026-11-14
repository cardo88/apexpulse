"""Test de contrato del normalizador OpenF1 y del endpoint race_control con 2026-monaco-r.

Usa el tramo grabado en fixtures/sessions/2026-monaco-r/openf1/ (14:15 a 15:15 UTC): SC desde la
vuelta 60 con paradas reales y pasadas por el pit lane, segundo SC en la 66, bandera roja en la
68 y reanudación. El crudo se baja con el adaptador contra OpenF1 simulado y después se normaliza.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from apexpulse.cli import main
from apexpulse.model import (
    NEUTRALIZED,
    IntervalUpdated,
    PitLane,
    RaceControlMessage,
    StintStarted,
    TrackStatus,
    TrackStatusChanged,
    read_events,
    read_meta,
    sort_key,
    write_events,
)
from apexpulse.session_id import SessionId
from apexpulse.sources import Normalized, OpenF1Adapter, SchemaError
from apexpulse.sources.openf1 import RATE_LIMITS
from apexpulse.sources.ratelimit import RateLimiter
from apexpulse.sources.rawstore import read_jsonl_zst
from conftest import FakeClock, FakeOpenF1

MONACO = SessionId.parse("2026-monaco-r")
SAO_PAULO = SessionId.parse("2026-sao-paulo-r")
AHORA = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)


def _adapter(openf1: FakeOpenF1, clock: FakeClock) -> OpenF1Adapter:
    limiter = RateLimiter(RATE_LIMITS, clock=clock, sleep=clock.sleep)
    return OpenF1Adapter(openf1.client(), limiter, sleep=clock.sleep, now=lambda: AHORA)


def _bajar_y_normalizar(
    openf1: FakeOpenF1, clock: FakeClock, raw: Path, session: SessionId = MONACO
) -> Normalized:
    adapter = _adapter(openf1, clock)
    adapter.fetch(session, raw)
    return adapter.normalize(session, raw)


def _hhmmss(t: datetime) -> str:
    return t.strftime("%H:%M:%S")


# race_control en el adaptador -------------------------------------------------------------


def test_race_control_se_descarga_y_cachea(
    tmp_path: Path, openf1_monaco: FakeOpenF1, clock: FakeClock
) -> None:
    report = _adapter(openf1_monaco, clock).fetch(MONACO, tmp_path)
    assert report.source_session_key == 11299
    assert report.warnings == []
    guardado = list(read_jsonl_zst(report.dest / "race_control.jsonl.zst"))
    assert guardado == openf1_monaco.endpoint_json("race_control")
    safety_car = [r["message"] for r in guardado if r["category"] == "SafetyCar"]
    assert safety_car == ["SAFETY CAR DEPLOYED", "SAFETY CAR IN THIS LAP", "SAFETY CAR DEPLOYED"]

    openf1_monaco.requests.clear()
    assert _adapter(openf1_monaco, clock).fetch(MONACO, tmp_path).from_cache
    assert openf1_monaco.requests == []


def test_race_control_sin_category_falla(
    tmp_path: Path, openf1_monaco: FakeOpenF1, clock: FakeClock
) -> None:
    def quitar(datos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{k: v for k, v in r.items() if k != "category"} for r in datos]

    openf1_monaco.edits["race_control"] = quitar
    with pytest.raises(SchemaError, match="race_control: el registro 0 no tiene category"):
        _adapter(openf1_monaco, clock).fetch(MONACO, tmp_path)


# Normalización ---------------------------------------------------------------------------


def test_estado_de_pista_derivado(
    tmp_path: Path, openf1_monaco: FakeOpenF1, clock: FakeClock
) -> None:
    resultado = _bajar_y_normalizar(openf1_monaco, clock, tmp_path)
    estados = sorted(
        (e for e in resultado.events if isinstance(e, TrackStatusChanged)), key=sort_key
    )
    assert [(_hhmmss(e.t), e.lap, e.status) for e in estados] == [
        ("14:20:02", 60, TrackStatus.SC),
        ("14:29:41", 65, TrackStatus.SC_ENDING),
        ("14:30:34", 65, TrackStatus.GREEN),
        ("14:31:18", 66, TrackStatus.SC),
        ("14:35:06", 68, TrackStatus.RED),
        ("15:12:00", 68, TrackStatus.GREEN),
    ]
    # Un TRACK CLEAR durante la bandera roja (15:00:48) no la termina.
    assert estados[4].cause == "SESSION ABORTED"
    assert estados[5].cause == "SESSION STARTED"


def test_paradas_bajo_safety_car(
    tmp_path: Path, openf1_monaco: FakeOpenF1, clock: FakeClock
) -> None:
    resultado = _bajar_y_normalizar(openf1_monaco, clock, tmp_path)
    estados = sorted(
        (e for e in resultado.events if isinstance(e, TrackStatusChanged)), key=sort_key
    )
    inicio_sc, fin_sc = estados[0].t, estados[2].t  # SC de la vuelta 60 hasta el verde
    bajo_sc = sorted(
        (e for e in resultado.events if isinstance(e, PitLane) and inicio_sc <= e.t < fin_sc),
        key=sort_key,
    )
    paradas = [(e.driver, e.lap, e.stationary_s) for e in bajo_sc if e.stationary_s is not None]
    assert paradas == [(44, 60, 8.6), (14, 58, 4.3), (63, 60, 5.5), (11, 59, 3.9), (5, 59, 2.5)]
    # "ALL CARS THROUGH THE PIT LANE": el resto son pasadas sin detención.
    pasadas = [e for e in bajo_sc if e.stationary_s is None]
    assert len(pasadas) == 18
    assert all(e.lane_s is not None and e.lane_s < 35 for e in pasadas)
    assert TrackStatus.SC in NEUTRALIZED and TrackStatus.SC_ENDING in NEUTRALIZED


def test_stints_e_intervalos(tmp_path: Path, openf1_monaco: FakeOpenF1, clock: FakeClock) -> None:
    resultado = _bajar_y_normalizar(openf1_monaco, clock, tmp_path)
    # BOR (5) pone blandos nuevos en la parada de la vuelta 59.
    bor = [e for e in resultado.events if isinstance(e, StintStarted) and e.driver == 5]
    assert (59, "SOFT", 0) in [(e.lap, e.compound.value, e.tyre_age) for e in bor]
    doblados = [e for e in resultado.events if isinstance(e, IntervalUpdated) and e.laps_down]
    assert doblados and all(e.gap_s is None for e in doblados)
    mensajes = [e for e in resultado.events if isinstance(e, RaceControlMessage)]
    assert len(mensajes) == len(openf1_monaco.endpoint_json("race_control"))
    assert resultado.meta.source_session_key == 11299
    assert resultado.meta.circuit == "Mónaco"


def test_parquet_ida_y_vuelta_determinista(
    tmp_path: Path, openf1_monaco: FakeOpenF1, clock: FakeClock
) -> None:
    resultado = _bajar_y_normalizar(openf1_monaco, clock, tmp_path / "raw")
    a, b = tmp_path / "a.parquet", tmp_path / "b.parquet"
    total = write_events(a, resultado.meta, resultado.events)
    write_events(b, resultado.meta, list(reversed(resultado.events)))
    assert total == len(resultado.events)
    assert a.read_bytes() == b.read_bytes()
    assert read_events(a) == sorted(resultado.events, key=sort_key)
    assert read_meta(a) == resultado.meta
    assert len(read_events(a, kinds=["track_status"])) == 6


def test_sao_paulo_sin_neutralizaciones(
    tmp_path: Path, openf1: FakeOpenF1, clock: FakeClock
) -> None:
    resultado = _bajar_y_normalizar(openf1, clock, tmp_path, SAO_PAULO)
    estados = [e for e in resultado.events if isinstance(e, TrackStatusChanged)]
    assert all(e.status not in NEUTRALIZED for e in estados)
    assert resultado.meta.source_session_key == 11412


def test_cli_normalize(
    tmp_path: Path,
    openf1_monaco: FakeOpenF1,
    clock: FakeClock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _adapter(openf1_monaco, clock).fetch(MONACO, tmp_path / "raw")
    assert main(["normalize", "2026-monaco-r", "--data-dir", str(tmp_path)]) == 0
    salida = capsys.readouterr().out
    assert "14:20:02  vuelta 60  SC         SAFETY CAR DEPLOYED" in salida
    assert (tmp_path / "canonical" / "2026-monaco-r.parquet").exists()


def test_cli_normalize_sin_crudo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["normalize", "2026-monaco-r", "--data-dir", str(tmp_path)]) == 1
    assert "make fetch SESSION=2026-monaco-r" in capsys.readouterr().err
