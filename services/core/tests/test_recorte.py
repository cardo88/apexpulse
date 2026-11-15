"""Tests del recorte de fixtures de OpenF1 con un crudo sintético de dos pilotos."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from apexpulse.cli import main
from apexpulse.sources.base import SourceError
from apexpulse.sources.openf1_recorte import Ventana, recortar_openf1
from apexpulse.sources.rawstore import write_jsonl_zst

INICIO = datetime(2026, 6, 7, 13, 0, tzinfo=UTC)


def _t(minutos: float) -> str:
    return (INICIO + timedelta(minutes=minutos)).isoformat()


def _vuelta(piloto: int, n: int, minuto: float, duracion: float | None = 60.0) -> dict[str, Any]:
    return {
        "driver_number": piloto,
        "lap_number": n,
        "date_start": _t(minuto),
        "lap_duration": duracion,
    }


def _stint(piloto: int, n: int, desde: int, hasta: int | None) -> dict[str, Any]:
    return {"driver_number": piloto, "stint_number": n, "lap_start": desde, "lap_end": hasta}


def _gap(piloto: int, minuto: float, gap: float | None) -> dict[str, Any]:
    return {
        "driver_number": piloto,
        "date": _t(minuto),
        "gap_to_leader": gap,
        "interval": gap,
    }


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    """Dos pilotos, vueltas de 1 minuto desde 13:00; el 2 abandona en la vuelta 4."""
    destino = tmp_path / "raw" / "2026" / "2026-monaco-r" / "openf1"
    crudo: dict[str, list[dict[str, Any]]] = {
        "drivers": [{"driver_number": 1}, {"driver_number": 2}],
        "laps": [
            *(_vuelta(1, n, n - 1) for n in range(1, 11)),
            *(_vuelta(2, n, n - 1) for n in range(1, 4)),
            _vuelta(2, 4, 3, duracion=None),  # abandono: sin tiempo ni vuelta siguiente
        ],
        "stints": [
            _stint(1, 1, 1, 4),
            _stint(1, 2, 5, None),
            _stint(2, 1, 1, 3),  # abandona antes del rango
        ],
        "pit": [
            {"driver_number": 1, "date": _t(3.5)},
            {"driver_number": 1, "date": _t(7.5)},
        ],
        "position": [
            {"driver_number": 1, "date": _t(-60), "position": 1},
            {"driver_number": 2, "date": _t(-60), "position": 2},
            {"driver_number": 2, "date": _t(2), "position": 3},
            {"driver_number": 1, "date": _t(2.5), "position": 2},
            {"driver_number": 2, "date": _t(6), "position": 1},
        ],
        "intervals": [
            _gap(1, 1, 0.0),
            _gap(2, 1, 1.5),
            _gap(1, 2, 2.0),
            _gap(1, 3, None),  # sin distancia: no sirve de arrastre
            _gap(1, 6, 0.5),
        ],
        "race_control": [{"date": _t(1)}, {"date": _t(6)}],
        "weather": [{"date": _t(1)}, {"date": _t(7)}],
    }
    endpoints = {}
    for endpoint, filas in crudo.items():
        archivo = f"{endpoint}.jsonl.zst"
        write_jsonl_zst(destino / archivo, filas)
        endpoints[endpoint] = {"file": archivo, "rows": len(filas)}
    manifiesto = {
        "endpoints": endpoints,
        "session": "2026-monaco-r",
        "openf1_session": {"meeting_key": 7, "date_start": INICIO.isoformat()},
    }
    (destino / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")
    write_jsonl_zst(
        tmp_path / "raw" / "2026" / "_openf1" / "sessions.jsonl.zst",
        [{"meeting_key": 7, "session_key": 1}, {"meeting_key": 8, "session_key": 2}],
    )
    return destino


def _leer(destino: Path, endpoint: str) -> list[dict[str, Any]]:
    datos: list[dict[str, Any]] = json.loads((destino / f"{endpoint}.json").read_text("utf-8"))
    return datos


def _ventana() -> Ventana:
    """Minutos 5 a 8 (vueltas 6 a 9), con la sesión empezando en el minuto 0."""
    return Ventana(INICIO + timedelta(minutes=5), INICIO + timedelta(minutes=8), 6, 9)


def test_position_trae_el_ultimo_previo_por_piloto_y_el_de_la_grilla(
    raw: Path, tmp_path: Path
) -> None:
    salida = tmp_path / "fixture"
    recortar_openf1(raw, salida, _ventana())
    filas = [(f["driver_number"], f["position"]) for f in _leer(salida, "position")]
    # Último antes de la ventana: piloto 2 -> P3 (minuto 2), piloto 1 -> P2 (minuto 2,5); los de
    # la grilla (minuto -60, anteriores al inicio de la sesión) quedan para el estado de arranque.
    assert filas == [(1, 1), (2, 2), (2, 3), (1, 2), (2, 1)]


def test_intervals_ignora_registros_sin_distancia_como_arrastre(raw: Path, tmp_path: Path) -> None:
    salida = tmp_path / "fixture"
    recortar_openf1(raw, salida, _ventana())
    filas = [(f["driver_number"], f["gap_to_leader"]) for f in _leer(salida, "intervals")]
    # El 1 llega con 2,0 s (su registro del minuto 3 no tiene distancia); el 2, con 1,5 s.
    assert filas == [(2, 1.5), (1, 2.0), (1, 0.5)]


def test_stints_incluye_el_ultimo_previo_de_quien_abandono(raw: Path, tmp_path: Path) -> None:
    salida = tmp_path / "fixture"
    recortar_openf1(raw, salida, _ventana())
    stints = {(f["driver_number"], f["stint_number"]) for f in _leer(salida, "stints")}
    assert stints == {(1, 2), (2, 1)}  # el stint 1 del piloto 1 terminó antes y no es el último


def test_laps_trae_el_rango_la_ultima_completada_y_las_que_fechan_stints(
    raw: Path, tmp_path: Path
) -> None:
    salida = tmp_path / "fixture"
    recortar_openf1(raw, salida, _ventana())
    vueltas = {(f["driver_number"], f["lap_number"]) for f in _leer(salida, "laps")}
    # 6 a 9, la 4 por ser la última completada antes de la ventana y la 5 por fechar el stint 2.
    esperado = {(1, n) for n in (4, 5, 6, 7, 8, 9)}
    esperado |= {(2, 3), (2, 1)}  # la última completada del que abandonó y la que fecha su stint
    assert vueltas == esperado


def test_pit_race_control_y_weather_solo_dentro_de_la_ventana(raw: Path, tmp_path: Path) -> None:
    salida = tmp_path / "fixture"
    recortar_openf1(raw, salida, _ventana())
    assert [f["date"] for f in _leer(salida, "pit")] == [_t(7.5)]
    assert [f["date"] for f in _leer(salida, "race_control")] == [_t(6)]
    assert [f["date"] for f in _leer(salida, "weather")] == [_t(7)]


def test_drivers_completo_y_sessions_del_mismo_fin_de_semana(raw: Path, tmp_path: Path) -> None:
    salida = tmp_path / "fixture"
    cantidades = recortar_openf1(raw, salida, _ventana())
    assert cantidades["drivers"] == 2
    assert _leer(salida, "sessions") == [{"meeting_key": 7, "session_key": 1}]


def test_los_registros_no_se_modifican_y_conservan_el_orden(raw: Path, tmp_path: Path) -> None:
    salida = tmp_path / "fixture"
    recortar_openf1(raw, salida, _ventana())
    fechas = [f["date"] for f in _leer(salida, "position")]
    assert fechas == sorted(fechas)
    assert _leer(salida, "laps")[0] == _vuelta(1, 4, 3)


def test_vaciar_escribe_endpoints_vacios_y_valida_los_nombres(raw: Path, tmp_path: Path) -> None:
    salida = tmp_path / "fixture"
    cantidades = recortar_openf1(
        raw, salida, _ventana(), vaciar=frozenset({"intervals", "weather"})
    )
    assert cantidades["intervals"] == cantidades["weather"] == 0
    assert (salida / "intervals.json").read_text("utf-8") == "[]\n"
    assert cantidades["position"] > 0
    with pytest.raises(SourceError, match="endpoints desconocidos"):
        recortar_openf1(raw, salida, _ventana(), vaciar=frozenset({"telemetry"}))


def test_un_registro_por_linea(raw: Path, tmp_path: Path) -> None:
    salida = tmp_path / "fixture"
    recortar_openf1(raw, salida, _ventana())
    lineas = (salida / "position.json").read_text("utf-8").splitlines()
    assert lineas[0] == "[" and lineas[-1] == "]"
    registros = [json.loads(linea.rstrip(",")) for linea in lineas[1:-1]]
    assert registros == _leer(salida, "position")
    assert all(linea.endswith(",") for linea in lineas[1:-2])


def test_ventana_invalida() -> None:
    desde = datetime(2026, 6, 7, 14, tzinfo=UTC)
    with pytest.raises(ValueError, match="zona horaria"):
        Ventana(datetime(2026, 6, 7, 14), desde, 1, 2)
    with pytest.raises(ValueError, match="hasta es anterior"):
        Ventana(desde, desde - timedelta(minutes=1), 1, 2)
    with pytest.raises(ValueError, match="vuelta final"):
        Ventana(desde, desde, 5, 4)


def test_sin_crudo_completo(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="correr make fetch"):
        recortar_openf1(tmp_path, tmp_path / "salida", _ventana())


def test_cli_fixture(raw: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    datos = raw.parents[3]
    salida = tmp_path / "fixture"
    argv = [
        *("fixture", "2026-monaco-r", "--data-dir", str(datos), "--salida", str(salida)),
        *("--desde", "2026-06-07T13:05", "--hasta", "2026-06-07T13:08", "--vueltas", "6-9"),
    ]
    assert main(argv) == 0
    assert "position.json" in capsys.readouterr().out
    assert (salida / "laps.json").exists()


def test_cli_fixture_con_ventana_invalida(
    raw: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        *("fixture", "2026-monaco-r", "--data-dir", str(raw.parents[3]), "--salida", str(tmp_path)),
        *("--desde", "2026-06-07T13:08", "--hasta", "2026-06-07T13:05", "--vueltas", "6-9"),
    ]
    assert main(argv) == 1
    assert "hasta es anterior a desde" in capsys.readouterr().err
