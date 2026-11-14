"""Tests del modelo canónico v1: validación de eventos, orden y Parquet."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from apexpulse.model import (
    SCHEMA_VERSION,
    Compound,
    Event,
    IntervalUpdated,
    LapCompleted,
    PitLane,
    PositionChanged,
    RaceControlMessage,
    SessionMeta,
    StintStarted,
    TrackStatus,
    TrackStatusChanged,
    WeatherSample,
    read_events,
    read_meta,
    sort_key,
    write_events,
)
from apexpulse.model.parquet import SCHEMA

T0 = datetime(2026, 6, 7, 14, 20, 2, tzinfo=UTC)

META = SessionMeta(
    session="2026-monaco-r",
    source="openf1",
    source_session_key=11299,
    circuit="Mónaco",
    start=datetime(2026, 6, 7, 13, 0, tzinfo=UTC),
    end=datetime(2026, 6, 7, 15, 0, tzinfo=UTC),
)


def _uno_de_cada() -> list[Event]:
    return [
        LapCompleted(t=T0, driver=12, lap=59, lap_time_s=78.4, s1_s=20.1, pit_out=False),
        StintStarted(t=T0, driver=5, lap=59, stint=5, compound=Compound.SOFT, tyre_age=0),
        PitLane(t=T0, driver=5, lap=59, lane_s=24.824, stationary_s=2.5),
        PositionChanged(t=T0, driver=12, position=1),
        IntervalUpdated(t=T0, driver=41, laps_down=1, interval_s=0.495),
        RaceControlMessage(
            t=T0, category="SafetyCar", message="SAFETY CAR DEPLOYED", lap=60, sector=None
        ),
        TrackStatusChanged(t=T0, status=TrackStatus.SC, lap=60, cause="SAFETY CAR DEPLOYED"),
        WeatherSample(t=T0, air_c=24.0, track_c=43.0, rain=False, wind_deg=193),
    ]


def test_version_del_esquema() -> None:
    assert SCHEMA_VERSION == "1.0"
    assert META.schema_version == "1.0"


def test_instante_sin_zona_falla() -> None:
    with pytest.raises(ValidationError, match="zona horaria"):
        PositionChanged(t=datetime(2026, 6, 7, 14, 0), driver=1, position=1)


def test_instante_se_lleva_a_utc() -> None:
    montevideo = timezone(timedelta(hours=-3))
    evento = PositionChanged(
        t=datetime(2026, 6, 7, 11, 20, 2, tzinfo=montevideo), driver=1, position=1
    )
    assert evento.t == T0 and evento.t.tzinfo == UTC


def test_campo_extra_y_valores_invalidos_fallan() -> None:
    with pytest.raises(ValidationError):
        PositionChanged(t=T0, driver=1, position=1, team="X")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        PitLane(t=T0, driver=5, lap=59, stationary_s=-1.0)
    with pytest.raises(ValidationError):
        PositionChanged(t=T0, driver=0, position=1)


def test_eventos_inmutables() -> None:
    evento = PositionChanged(t=T0, driver=1, position=1)
    with pytest.raises(ValidationError):
        evento.position = 2


def test_orden_de_desempate() -> None:
    eventos = sorted(reversed(_uno_de_cada()), key=sort_key)
    assert [e.kind for e in eventos] == [
        "race_control",
        "track_status",
        "lap",
        "pit",
        "stint",
        "position",
        "interval",
        "weather",
    ]


def test_parquet_ida_y_vuelta(tmp_path: Path) -> None:
    destino = tmp_path / "canonical" / "2026-monaco-r.parquet"
    eventos = _uno_de_cada()
    assert write_events(destino, META, eventos) == len(eventos)
    assert read_events(destino) == sorted(eventos, key=sort_key)
    assert read_meta(destino) == META
    assert [e.kind for e in read_events(destino, kinds=["pit", "weather"])] == ["pit", "weather"]
    assert not destino.with_suffix(".parquet.tmp").exists()


def test_parquet_columnas_fijas(tmp_path: Path) -> None:
    destino = tmp_path / "s.parquet"
    write_events(destino, META, _uno_de_cada())
    tabla = pq.read_table(destino)
    assert tabla.schema.names == SCHEMA.names
    assert tabla.column("seq").to_pylist() == list(range(8))
    assert tabla.column("kind").to_pylist()[:2] == ["race_control", "track_status"]


def test_archivo_ajeno_falla(tmp_path: Path) -> None:
    import pyarrow as pa

    ajeno = tmp_path / "otro.parquet"
    pq.write_table(pa.table({"x": [1]}), ajeno)
    with pytest.raises(ValueError, match="falta la cabecera"):
        read_meta(ajeno)
