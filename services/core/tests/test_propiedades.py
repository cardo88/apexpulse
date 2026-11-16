"""Propiedades de `undercut_window` sobre carreras reales (fixtures) y, si existen, completas.

Cada propiedad vale para cualquier sesión, no para un caso: se comprueba sobre Mónaco, Australia
y São Paulo, y sobre las sesiones completas de `data/canonical` cuando están en la compu (en CI
no están y esos casos se saltean).

- Causalidad: cortar la secuencia en el punto k da exactamente las lecturas que la secuencia
  completa tenía antes de k; lo que viene después no las cambia.
- Una lectura por pareja y stint: ni dos con la misma clave ni dos con los mismos pilotos y
  stint del perseguidor.
- Estabilidad tras seek: llegar a un punto por seek, hacia adelante o hacia atrás, y seguir da
  las mismas lecturas que la reproducción continua, sin repetir las anteriores.
- Vuelta mínima: ninguna lectura sale con el perseguidor por debajo de `min_lap`.
"""

from __future__ import annotations

import tomllib
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timedelta
from importlib import resources
from pathlib import Path

import pytest

from apexpulse.model import Event, read_events
from apexpulse.readings import Engine, Reading, load_config, load_messages
from apexpulse.replay import FakeClock, RaceState, Replay
from conftest import RAIZ
from helpers import FIXTURES_POR_SESION, correr_pipeline

REGLA = "undercut_window"
COMPLETAS = RAIZ / "data" / "canonical"


@pytest.fixture(scope="module")
def parquets(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return {s: correr_pipeline(s, tmp_path_factory.mktemp(s)).parquet for s in FIXTURES_POR_SESION}


def _completa(sesion: str) -> Path:
    path = COMPLETAS / f"{sesion}.parquet"
    if not path.exists():
        pytest.skip(f"no hay {path}: correr make fetch y make normalize")
    return path


def _plegar(eventos: Sequence[Event], engine: Engine | None = None) -> list[tuple[int, Reading]]:
    """Alimenta estado y motor evento por evento, como el replay; devuelve (índice, lectura)."""
    engine = Engine.default() if engine is None else engine
    estado = RaceState()
    salida: list[tuple[int, Reading]] = []
    for i, evento in enumerate(eventos):
        estado.apply(evento)
        salida += [(i, lectura) for lectura in engine.process(evento, estado)]
    return salida


def _undercut(lecturas: Sequence[Reading]) -> list[Reading]:
    return [r for r in lecturas if r.rule == REGLA]


def _con_minimo(minimo: int) -> Engine:
    datos = tomllib.loads(
        resources.files("apexpulse").joinpath("config/readings.toml").read_text("utf-8")
    )
    datos["undercut_window"]["min_lap"] = minimo
    return Engine(load_config(datos), load_messages())


def _correr(replay: Replay) -> list[Reading]:
    return [lectura for lote in replay.run() for paso in lote for lectura in paso.readings]


def _replay(path: Path, engine: Engine | None = None) -> Replay:
    return Replay.from_parquet(
        path, FakeClock(), speed=None, engine=Engine.default() if engine is None else engine
    )


# Causalidad ------------------------------------------------------------------------------------


@pytest.mark.parametrize("sesion", list(FIXTURES_POR_SESION))
def test_causalidad_cortar_la_secuencia_no_cambia_lo_ya_emitido(
    sesion: str, parquets: dict[str, Path]
) -> None:
    eventos = list(read_events(parquets[sesion]))
    completa = _plegar(eventos)
    emitidas = [i for i, _ in completa]
    # Cada corte justo antes y justo después de una emisión (muestra de hasta 8), más el centro.
    muestra = emitidas[:: max(1, len(emitidas) // 8)]
    cortes = sorted({k for i in muestra for k in (i, i + 1)} | {len(eventos) // 2})
    for k in cortes:
        assert [(i, r) for i, r in completa if i < k] == _plegar(eventos[:k]), k


def test_causalidad_el_futuro_no_cambia_el_pasado(parquets: dict[str, Path]) -> None:
    """Con tres futuros distintos después de k, el pasado hasta k es el mismo."""
    eventos = list(read_events(parquets["2026-sao-paulo-r"]))
    k = len(eventos) * 2 // 3
    pasado = _plegar(eventos[:k])
    assert _plegar(eventos[: k + 500])[: len(pasado)] == pasado
    assert [x for x in _plegar(eventos) if x[0] < k] == pasado


# Una lectura por pareja y stint ----------------------------------------------------------------


def _pareja_y_stint(r: Reading) -> tuple[tuple[int, ...], str]:
    return r.drivers, r.key.rsplit(":", 1)[1]


def _una_por_pareja_y_stint(lecturas: Sequence[Reading]) -> None:
    undercut = _undercut(lecturas)
    assert undercut
    claves = Counter(r.key for r in undercut)
    assert max(claves.values()) == 1
    assert max(Counter(_pareja_y_stint(r) for r in undercut).values()) == 1
    for r in undercut:
        assert r.key == f"{REGLA}:{r.drivers[0]}:{r.drivers[1]}:{_pareja_y_stint(r)[1]}"


def test_una_lectura_por_pareja_y_stint_en_los_fixtures(parquets: dict[str, Path]) -> None:
    """Por sesión: la `key` no lleva el identificador de sesión, así que poner todo junto en
    una sola lista puede chocar por casualidad (mismos números de piloto, pareja y stint, en
    dos carreras). Mónaco no ejercita `undercut_window` (ver test_pipeline.py); se saltea."""
    probadas = 0
    for parquet in parquets.values():
        lecturas = [r for _, r in _plegar(list(read_events(parquet)))]
        if not _undercut(lecturas):
            continue
        _una_por_pareja_y_stint(lecturas)
        probadas += 1
    assert probadas > 0


@pytest.mark.parametrize("sesion", list(FIXTURES_POR_SESION))
def test_una_lectura_por_pareja_y_stint_en_la_carrera_completa(sesion: str) -> None:
    eventos = list(read_events(_completa(sesion)))
    _una_por_pareja_y_stint([r for _, r in _plegar(eventos)])


# Estabilidad tras seek -------------------------------------------------------------------------


def _puntos(lecturas: Sequence[Reading]) -> list[datetime]:
    muestra = lecturas[:: max(1, len(lecturas) // 6)]
    puntos: list[datetime] = []
    for r in muestra:
        puntos += [r.t - timedelta(seconds=1), r.t, r.t + timedelta(microseconds=1)]
    return puntos


@pytest.mark.parametrize("sesion", ["2026-australia-r", "2026-sao-paulo-r"])
def test_seek_mantiene_las_lecturas_de_undercut(sesion: str, parquets: dict[str, Path]) -> None:
    path = parquets[sesion]
    continua = _undercut(_correr(_replay(path)))
    assert continua
    for punto in _puntos(continua):
        replay = _replay(path)
        replay.seek(punto)
        assert _undercut(_correr(replay)) == [r for r in continua if r.t >= punto]


@pytest.mark.parametrize("sesion", ["2026-australia-r", "2026-sao-paulo-r"])
def test_seek_hacia_atras_y_adelante_converge_a_la_misma_salida(
    sesion: str, parquets: dict[str, Path]
) -> None:
    path = parquets[sesion]
    continua = _undercut(_correr(_replay(path)))
    medio, final = continua[len(continua) // 2].t, continua[-1].t + timedelta(seconds=1)
    replay = _replay(path)
    replay.seek(final)
    assert _undercut(list(replay.engine.history)) == continua  # type: ignore[union-attr]
    replay.seek(medio)
    assert _undercut(list(replay.engine.history)) == [r for r in continua if r.t < medio]  # type: ignore[union-attr]
    assert _undercut(_correr(replay)) == [r for r in continua if r.t >= medio]


# Vuelta mínima ---------------------------------------------------------------------------------

MINIMOS = [1, 5, 12, 20, 40]


@pytest.mark.parametrize("sesion", list(FIXTURES_POR_SESION))
def test_ninguna_lectura_sale_por_debajo_de_la_vuelta_minima(
    sesion: str, parquets: dict[str, Path]
) -> None:
    eventos = list(read_events(parquets[sesion]))
    for minimo in MINIMOS:
        for _, r in _plegar(eventos, _con_minimo(minimo)):
            if r.rule == REGLA:
                assert r.evidence_value("vuelta_perseguidor") >= minimo  # type: ignore[operator]


@pytest.mark.parametrize("sesion", list(FIXTURES_POR_SESION))
def test_el_minimo_de_5_no_cambia_la_salida_de_los_fixtures(
    sesion: str, parquets: dict[str, Path]
) -> None:
    """Con juegos nuevos la edad mínima ya deja la primera lectura en la vuelta 12."""
    eventos = list(read_events(parquets[sesion]))
    assert _plegar(eventos, _con_minimo(5)) == _plegar(eventos, _con_minimo(1))


@pytest.mark.parametrize("sesion", list(FIXTURES_POR_SESION))
def test_la_vuelta_minima_en_carreras_completas(sesion: str) -> None:
    eventos = list(read_events(_completa(sesion)))
    for minimo in (5, 15):
        for _, r in _plegar(eventos, _con_minimo(minimo)):
            if r.rule == REGLA:
                assert r.evidence_value("vuelta_perseguidor") >= minimo  # type: ignore[operator]


# La ventana del fixture coincide con la carrera completa -----------------------------------
# (H2 t2): un fixture recortado no puede inventar ni perder lecturas dentro de su propia
# ventana. Solo para sesiones con una carrera completa en data/canonical (se saltea en CI).

VUELTA_HASTA = {"2026-barcelona-r": 14, "2026-hungria-r": 14}


@pytest.mark.parametrize("sesion", list(VUELTA_HASTA))
def test_las_lecturas_del_fixture_coinciden_con_la_completa_filtrada_a_la_ventana(
    sesion: str, parquets: dict[str, Path]
) -> None:
    del_fixture = [r for _, r in _plegar(list(read_events(parquets[sesion])))]
    de_la_completa = [r for _, r in _plegar(list(read_events(_completa(sesion))))]
    hasta = VUELTA_HASTA[sesion]
    assert del_fixture == [r for r in de_la_completa if r.lap <= hasta]
