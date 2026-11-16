"""Test de contrato del normalizador OpenF1 y del endpoint race_control con 2026-monaco-r.

Usa el tramo grabado en fixtures/sessions/2026-monaco-r/openf1/ (14:15 a 15:15 UTC): SC desde la
vuelta 60 con paradas reales y pasadas por el pit lane, segundo SC en la 66, bandera roja en la
68 y reanudación. El crudo se baja con el adaptador contra OpenF1 simulado y después se normaliza.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from apexpulse.cli import main
from apexpulse.model import (
    NEUTRALIZED,
    DriverInfo,
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
from conftest import OPENF1_MONACO, FakeClock, FakeOpenF1, normalizar_fixture

MONACO = SessionId.parse("2026-monaco-r")
SAO_PAULO = SessionId.parse("2026-sao-paulo-r")
AHORA = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)
MONACO_FIXTURE = OPENF1_MONACO


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


def test_pilotos_de_monaco(tmp_path: Path, openf1_monaco: FakeOpenF1, clock: FakeClock) -> None:
    resultado = _bajar_y_normalizar(openf1_monaco, clock, tmp_path)
    assert not any(w.startswith("drivers") for w in resultado.warnings)
    pilotos = {e.driver: e for e in resultado.events if isinstance(e, DriverInfo)}
    assert len(pilotos) == 22
    assert all(e.t == resultado.meta.start for e in pilotos.values())
    assert pilotos[44] == DriverInfo(
        t=resultado.meta.start, driver=44, acronym="HAM", name="Lewis Hamilton", team="Ferrari"
    )
    assert pilotos[31].acronym == "OCO"  # en Mónaco corre OCO; en São Paulo, CAM (51)

    # Las paradas reales bajo el SC de la vuelta 60, con su código de 3 letras.
    estados = sorted(
        (e for e in resultado.events if isinstance(e, TrackStatusChanged)), key=sort_key
    )
    inicio_sc, fin_sc = estados[0].t, estados[2].t
    paradas = sorted(
        (
            e
            for e in resultado.events
            if isinstance(e, PitLane) and e.stationary_s is not None and inicio_sc <= e.t < fin_sc
        ),
        key=sort_key,
    )
    assert [pilotos[e.driver].acronym for e in paradas] == ["HAM", "ALO", "RUS", "PER", "BOR"]


def test_drivers_invalidos_y_repetidos_avisan(
    tmp_path: Path, openf1_monaco: FakeOpenF1, clock: FakeClock
) -> None:
    def editar(datos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sin_sigla = {**datos[0], "name_acronym": None}
        sin_equipo = {**datos[1], "team_name": None}
        repetido = {**datos[2], "team_name": "Otro equipo"}
        return [sin_sigla, sin_equipo, *datos[2:], repetido]

    openf1_monaco.edits["drivers"] = editar
    resultado = _bajar_y_normalizar(openf1_monaco, clock, tmp_path)
    pilotos = {e.driver: e for e in resultado.events if isinstance(e, DriverInfo)}
    assert 1 not in pilotos and len(pilotos) == 21
    assert pilotos[3].team is None
    assert pilotos[5].team == "Otro equipo"
    avisos = [w for w in resultado.warnings if w.startswith("drivers")]
    assert avisos == [
        "drivers: name_acronym ausente o no es de 3 letras, omitidos: 1 "
        "(por ejemplo piloto 1 None)",
        "drivers: número repetido con datos distintos, queda el último: 1 "
        "(por ejemplo piloto 5 BOR y BOR)",
    ]


def test_crudo_sin_drivers_normaliza_con_aviso(
    tmp_path: Path, openf1_monaco: FakeOpenF1, clock: FakeClock
) -> None:
    adapter = _adapter(openf1_monaco, clock)
    report = adapter.fetch(MONACO, tmp_path)
    manifiesto = report.dest / "manifest.json"
    datos = json.loads(manifiesto.read_text(encoding="utf-8"))
    del datos["endpoints"]["drivers"]
    manifiesto.write_text(json.dumps(datos), encoding="utf-8")

    resultado = adapter.normalize(MONACO, tmp_path)
    assert not any(isinstance(e, DriverInfo) for e in resultado.events)
    assert (
        "drivers: el crudo no tiene drivers, sin pilotos: 1 "
        "(por ejemplo correr make fetch SESSION=2026-monaco-r)"
    ) in resultado.warnings


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


def test_normalizador_avisa_cuando_omite_un_stint_sin_tyre_age_at_start(
    tmp_path: Path, clock: FakeClock
) -> None:
    """Un stint sin `tyre_age_at_start` se omite y el aviso dice cuántos y cuál (por ejemplo)."""
    origen = tmp_path / "fixture"
    shutil.copytree(MONACO_FIXTURE, origen)
    archivo = origen / "stints.json"
    filas = json.loads(archivo.read_text(encoding="utf-8"))
    total = len(filas)
    for fila in filas[:3]:
        fila["tyre_age_at_start"] = None
    archivo.write_text(json.dumps(filas), encoding="utf-8")

    resultado = normalizar_fixture(origen, "2026-monaco-r", tmp_path / "raw")

    avisos = [a for a in resultado.warnings if a.startswith("stints: sin tyre_age_at_start")]
    assert len(avisos) == 1
    assert "omitidos: 3 (por ejemplo piloto" in avisos[0]
    assert sum(isinstance(e, StintStarted) for e in resultado.events) == total - 3


def test_normalizador_no_avisa_de_tyre_age_si_el_crudo_la_trae(tmp_path: Path) -> None:
    resultado = normalizar_fixture(MONACO_FIXTURE, "2026-monaco-r", tmp_path / "raw")
    assert not [a for a in resultado.warnings if "tyre_age_at_start" in a]


def test_pit_sin_vuelta_anterior_conocida_usa_el_lap_number_crudo(tmp_path: Path) -> None:
    """Sin una vuelta de `laps` anterior a la pasada, se usa el `lap_number` crudo con aviso."""
    origen = tmp_path / "fixture"
    shutil.copytree(MONACO_FIXTURE, origen)
    archivo = origen / "pit.json"
    filas = json.loads(archivo.read_text(encoding="utf-8"))
    piloto = filas[0]["driver_number"]
    filas[0]["date"] = "2026-06-07T10:00:00.000000+00:00"  # antes de la primera vuelta del recorte
    archivo.write_text(json.dumps(filas), encoding="utf-8")

    resultado = normalizar_fixture(origen, "2026-monaco-r", tmp_path / "raw")

    avisos = [a for a in resultado.warnings if a.startswith("pit: vuelta no derivable")]
    assert len(avisos) == 1
    assert f"piloto {piloto}" in avisos[0]
    pasadas = [e for e in resultado.events if isinstance(e, PitLane) and e.driver == piloto]
    pasada = next(p for p in pasadas if p.t.hour == 10)
    assert pasada.lap == filas[0]["lap_number"]


def test_pit_en_la_vuelta_1_deriva_vuelta_0(tmp_path: Path) -> None:
    """Límite conocido: sin una vuelta anterior a la primera, la resta de 1 da 0, no 1.

    `_vuelta_de_piloto` asume que `pit.date` llega después del cruce que abre la vuelta
    siguiente a la de la pasada (verificado contra el stint nuevo de cada pasada real en las
    tres carreras, ver docs/lecturas.md). En la vuelta 1 no hay una vuelta anterior con la que
    contrastar esa hipótesis: el resultado es 0, no 1. Ninguna de las tres carreras de prueba
    tiene una parada en la vuelta 1; si aparece una real, este resultado hay que revisarlo con
    el dato en mano.
    """
    origen = tmp_path / "fixture"
    shutil.copytree(MONACO_FIXTURE, origen)
    archivo = origen / "pit.json"
    filas = json.loads(archivo.read_text(encoding="utf-8"))
    # Piloto 1: lap_start de su primer stint es la vuelta 1 (13:03:11.903, dura 91,069 s).
    filas.append(
        {
            "date": "2026-06-07T13:03:30.000000+00:00",
            "session_key": 11299,
            "pit_duration": 20.0,
            "stop_duration": 3.0,
            "lap_number": 1,
            "meeting_key": 1286,
            "driver_number": 1,
            "lane_duration": 20.0,
        }
    )
    archivo.write_text(json.dumps(filas), encoding="utf-8")

    resultado = normalizar_fixture(origen, "2026-monaco-r", tmp_path / "raw")

    pasada = next(
        e
        for e in resultado.events
        if isinstance(e, PitLane) and e.driver == 1 and e.t.minute == 3 and e.t.second == 30
    )
    assert pasada.lap == 0


def test_pit_bajo_bandera_roja_con_horas_sin_vueltas_no_rompe_la_derivacion(
    tmp_path: Path,
) -> None:
    """La pasada de HAM durante la bandera roja (2156 s en el pit lane) deriva la vuelta 68.

    Ninguna vuelta empieza durante la suspensión: el hueco entre vueltas conocidas no afecta
    la búsqueda de la última vuelta iniciada antes de la pasada.
    """
    resultado = normalizar_fixture(MONACO_FIXTURE, "2026-monaco-r", tmp_path / "raw")
    pasada = next(
        e
        for e in resultado.events
        if isinstance(e, PitLane) and e.driver == 44 and e.lane_s is not None and e.lane_s > 2000
    )
    assert pasada.lap == 68


def test_pit_en_el_instante_exacto_de_un_inicio_de_vuelta_deriva_la_vuelta_anterior(
    tmp_path: Path,
) -> None:
    """`date` igual al inicio de una vuelta cuenta como posterior al cruce (`<=`), no anterior."""
    origen = tmp_path / "fixture"
    shutil.copytree(MONACO_FIXTURE, origen)
    archivo = origen / "pit.json"
    filas = json.loads(archivo.read_text(encoding="utf-8"))
    # Piloto 44 empieza la vuelta 61 exactamente en este instante (dato real del fixture).
    inicio_vuelta_61 = "2026-06-07T14:21:25.510000+00:00"
    filas.append(
        {
            "date": inicio_vuelta_61,
            "session_key": 11299,
            "pit_duration": 20.0,
            "stop_duration": 3.0,
            "lap_number": 99,  # deliberadamente distinto, para que la derivación no lo copie
            "meeting_key": 1286,
            "driver_number": 44,
            "lane_duration": 20.0,
        }
    )
    archivo.write_text(json.dumps(filas), encoding="utf-8")

    resultado = normalizar_fixture(origen, "2026-monaco-r", tmp_path / "raw")

    pasada = next(
        e
        for e in resultado.events
        if isinstance(e, PitLane) and e.driver == 44 and e.t.isoformat() == inicio_vuelta_61
    )
    assert pasada.lap == 60
