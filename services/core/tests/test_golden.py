"""Golden de `cheap_stop` sobre las tres carreras con fixtures y los casos que lo explican.

El golden fija la salida completa (clave, instante, vuelta, evidencia y texto). Cambia solo con
`make golden-update`, revisando el diff. Los tests de abajo dicen qué significa cada archivo, así
que un golden mal regenerado no pasa por "lo que salga".

Casos (VSC de Australia por la vuelta del líder en que se desplegó):
- vuelta 12: positivo, 10 paradas con detención bajo VSC;
- vuelta 18: positivo, 3 paradas con detención bajo VSC (el cambio de neumáticos sin
  `stop_duration` de VER quedó fuera: su pasada fue en `VSC_ENDING`, que ya no cuenta);
- vuelta 34: negativo limpio. La única pasada del período (BOR, 04:53:09, 2 s antes de
  `TRACK CLEAR`) fue en `VSC_ENDING`, que no cuenta como neutralización para `cheap_stop`
  desde H2 (decisión del autor, docs/lecturas.md). `SC_ENDING` sí sigue contando.
- São Paulo: cero lecturas, sin Safety Car ni VSC.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from apexpulse.model import TrackStatus, TrackStatusChanged, read_events
from apexpulse.readings import Reading
from helpers import Corrida, correr_pipeline, lecturas_a_json, verificar_golden

SESIONES = ["2026-monaco-r", "2026-australia-r", "2026-sao-paulo-r"]


@pytest.fixture(scope="module")
def corridas(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Corrida]:
    return {s: correr_pipeline(s, tmp_path_factory.mktemp(s)) for s in SESIONES}


def _cheap_stop(corrida: Corrida) -> list[Reading]:
    return [r for r in corrida.readings if r.rule == "cheap_stop"]


@pytest.mark.parametrize("sesion", SESIONES)
def test_golden_de_cheap_stop(
    sesion: str, corridas: dict[str, Corrida], request: pytest.FixtureRequest
) -> None:
    obtenido = lecturas_a_json(_cheap_stop(corridas[sesion]))
    verificar_golden(f"{sesion}.cheap_stop.json", obtenido, request)


def test_sao_paulo_no_tiene_lecturas_de_cheap_stop(corridas: dict[str, Corrida]) -> None:
    assert _cheap_stop(corridas["2026-sao-paulo-r"]) == []
    assert lecturas_a_json([]) == "[]\n"


def test_monaco_tiene_8_lecturas_todas_bajo_safety_car(corridas: dict[str, Corrida]) -> None:
    lecturas = _cheap_stop(corridas["2026-monaco-r"])
    assert len(lecturas) == 8
    assert {r.evidence_value("estado_de_pista") for r in lecturas} == {"SC"}
    assert lecturas[0].text == (
        "HAM para bajo Safety Car en la vuelta 61: 8,6 s detenido y 31,2 s en pit lane."
    )


def _periodos(parquet: Path) -> list[tuple[datetime, int | None, TrackStatus]]:
    """Cambios de estado de pista como (instante, vuelta que abrió el período, estado)."""
    cambios = sorted(
        (
            e
            for e in read_events(parquet, kinds=["track_status"])
            if isinstance(e, TrackStatusChanged)
        ),
        key=lambda e: e.t,
    )
    salida: list[tuple[datetime, int | None, TrackStatus]] = []
    apertura: int | None = None
    for c in cambios:
        if c.status == TrackStatus.VSC:
            apertura = c.lap
        salida.append((c.t, apertura, c.status))
    return salida


def _por_periodo_vsc(corrida: Corrida) -> dict[tuple[int | None, str], int]:
    periodos = _periodos(corrida.parquet)
    cuenta: dict[tuple[int | None, str], int] = {}
    for r in _cheap_stop(corrida):
        pasada = datetime.fromisoformat(str(r.evidence_value("instante_pasada")))
        _, apertura, estado = [p for p in periodos if p[0] <= pasada][-1]
        clave = (apertura, estado.value)
        cuenta[clave] = cuenta.get(clave, 0) + 1
    return cuenta


def test_australia_vsc_de_las_vueltas_12_y_18_son_positivos(corridas: dict[str, Corrida]) -> None:
    cuenta = _por_periodo_vsc(corridas["2026-australia-r"])
    assert sum(n for (vuelta, _), n in cuenta.items() if vuelta == 12) == 10
    assert sum(n for (vuelta, _), n in cuenta.items() if vuelta == 18) == 4
    assert {e for (v, e) in cuenta if v in (12, 18)} == {"VSC"}


def test_australia_vsc_de_la_vuelta_34_es_negativo(corridas: dict[str, Corrida]) -> None:
    cuenta = _por_periodo_vsc(corridas["2026-australia-r"])
    assert cuenta.get((34, "VSC"), 0) == 0
    assert (34, "VSC_ENDING") not in cuenta  # BOR: VSC_ENDING ya no cuenta, no deja lectura
    lecturas = _cheap_stop(corridas["2026-australia-r"])
    assert [r for r in lecturas if r.drivers == (5,)] == []
