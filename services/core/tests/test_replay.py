"""Tests del reloj de replay con 2026-monaco-r como caso principal, sin esperas reales.

El Parquet se arma como en producción: OpenF1 simulado con las respuestas grabadas, el adaptador
baja el crudo, el normalizador lo convierte y `write_events` lo guarda. El reloj es `FakeClock`:
cada espera queda registrada y el tiempo avanza sin dormir.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import pytest

from apexpulse.cli import main
from apexpulse.model import (
    LapCompleted,
    PitLane,
    PositionChanged,
    RaceControlMessage,
    SessionMeta,
    TrackStatus,
    TrackStatusChanged,
    read_events,
    read_meta,
    sort_key,
    write_events,
)
from apexpulse.replay import FakeClock, RaceState, Replay, ReplayError, Step
from apexpulse.session_id import SessionId
from apexpulse.sources import Normalized, OpenF1Adapter
from apexpulse.sources.openf1 import RATE_LIMITS
from apexpulse.sources.ratelimit import RateLimiter
from conftest import OPENF1_MONACO, OPENF1_SAO_PAULO, FakeOpenF1

AHORA = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)
ROJA = datetime(2026, 6, 7, 14, 35, 6, 971000, tzinfo=UTC)
REANUDACION = datetime(2026, 6, 7, 15, 12, 0, 71000, tzinfo=UTC)


def _normalizar(directorio: Path, session: str, raw: Path) -> Normalized:
    clock = FakeClock()
    fake = FakeOpenF1(directorio, clock)
    limiter = RateLimiter(RATE_LIMITS, clock=clock, sleep=clock.sleep)
    adapter = OpenF1Adapter(fake.client(), limiter, sleep=clock.sleep, now=lambda: AHORA)
    sid = SessionId.parse(session)
    adapter.fetch(sid, raw)
    return adapter.normalize(sid, raw)


@pytest.fixture(scope="module")
def monaco(tmp_path_factory: pytest.TempPathFactory) -> tuple[Normalized, Path]:
    datos = tmp_path_factory.mktemp("monaco")
    resultado = _normalizar(OPENF1_MONACO, "2026-monaco-r", datos / "raw")
    destino = datos / "canonical" / "2026-monaco-r.parquet"
    write_events(destino, resultado.meta, resultado.events)
    return resultado, destino


@pytest.fixture(scope="module")
def sao_paulo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    datos = tmp_path_factory.mktemp("sao-paulo")
    resultado = _normalizar(OPENF1_SAO_PAULO, "2026-sao-paulo-r", datos / "raw")
    destino = datos / "canonical" / "2026-sao-paulo-r.parquet"
    write_events(destino, resultado.meta, resultado.events)
    return destino


@pytest.fixture
def parquet(monaco: tuple[Normalized, Path]) -> Path:
    return monaco[1]


def _pasos(replay: Replay) -> list[Step]:
    return [paso for lote in replay.run() for paso in lote]


def _plegar(path: Path, hasta: datetime) -> RaceState:
    estado = RaceState()
    for evento in read_events(path):
        if evento.t < hasta:
            estado.apply(evento)
    return estado


# Orden -----------------------------------------------------------------------------------


def test_orden_coincide_con_el_normalizador(
    monaco: tuple[Normalized, Path], clock: FakeClock
) -> None:
    resultado, path = monaco
    replay = Replay.from_parquet(path, clock, speed=None)
    emitidos = [paso.event for paso in _pasos(replay)]
    esperado = sorted(resultado.events, key=sort_key)
    # La largada (13:00) es posterior al primer evento del recorte: lo previo se pliega.
    previos = [e for e in esperado if e.t < resultado.meta.start]
    assert previos == []
    assert emitidos == esperado
    assert emitidos == read_events(path)
    assert clock.sleeps == []


def test_lotes_agrupan_eventos_simultaneos(parquet: Path, clock: FakeClock) -> None:
    lotes = list(Replay.from_parquet(parquet, clock, speed=None).run())
    for lote in lotes:
        assert len({paso.event.t for paso in lote}) == 1
    instantes = [lote[0].event.t for lote in lotes]
    assert instantes == sorted(set(instantes))
    # Los 22 eventos `driver` llegan juntos con la largada.
    assert [p.event.kind for p in lotes[0]] == ["driver"] * 22


def test_parquet_desordenado_se_rechaza(parquet: Path, clock: FakeClock) -> None:
    eventos = read_events(parquet)
    eventos[10], eventos[500] = eventos[500], eventos[10]
    with pytest.raises(ReplayError, match="fuera de orden en la fila"):
        Replay(read_meta(parquet), eventos, clock)


def test_version_mayor_distinta_se_rechaza(parquet: Path, clock: FakeClock) -> None:
    meta = read_meta(parquet).model_copy(update={"schema_version": "2.0"})
    with pytest.raises(ReplayError, match=r"el replay espera 1\.x"):
        Replay(meta, read_events(parquet), clock)


def test_velocidad_invalida(parquet: Path, clock: FakeClock) -> None:
    with pytest.raises(ReplayError, match="mayor que 0"):
        Replay.from_parquet(parquet, clock, speed=0)


# Esperas ---------------------------------------------------------------------------------


def test_esperas_a_x30_suman_el_tiempo_de_sesion(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=30)
    inicio = clock.t
    instantes = [lote[0].event.t for lote in replay.run()]
    total = (instantes[-1] - replay.meta.start).total_seconds()
    assert sum(clock.sleeps) == pytest.approx(total / 30, rel=1e-9)
    assert clock.t - inicio == pytest.approx(total / 30, rel=1e-9)
    assert max(clock.sleeps) <= 0.5  # max_sleep_s por defecto


def test_cada_lote_sale_cuando_vence(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=30)
    inicio = clock.t
    for n, lote in enumerate(replay.run()):
        transcurrido = (lote[0].event.t - replay.meta.start).total_seconds() / 30
        assert clock.t - inicio == pytest.approx(transcurrido, abs=1e-6)
        if n == 200:
            break


def test_sin_espera_no_duerme(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=None)
    assert replay.due_in() == 0.0
    assert len(_pasos(replay)) == len(read_events(parquet))
    assert clock.sleeps == []
    assert replay.finished
    assert replay.due_in() is None


def test_max_gap_recorta_la_bandera_roja(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=1, max_gap_s=30)
    replay.seek(ROJA)
    instantes: list[datetime] = []
    inicio = clock.t
    for lote in replay.run():
        instantes.append(lote[0].event.t)
        if lote[0].event.t >= REANUDACION:
            break
    huecos = [(b - a).total_seconds() for a, b in pairwise(instantes)]
    assert max(huecos) > 59  # muestras de clima cada 60 s durante la suspensión
    esperado = sum(min(h, 30.0) for h in huecos)
    assert clock.t - inicio == pytest.approx(esperado, rel=1e-6)
    sin_recorte = (REANUDACION - ROJA).total_seconds()
    assert clock.t - inicio < sin_recorte * 0.7


def test_max_gap_none_no_recorta(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=60)
    replay.seek(ROJA)
    inicio = clock.t
    for lote in replay.run():
        if lote[0].event.t >= REANUDACION:
            break
    assert clock.t - inicio == pytest.approx((REANUDACION - ROJA).total_seconds() / 60, rel=1e-6)


# Pausa y velocidad -----------------------------------------------------------------------


def test_pausa_congela_la_posicion(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=10)
    clock.sleep(3)
    antes = replay.position
    assert antes == replay.meta.start + timedelta(seconds=30)
    replay.pause()
    clock.sleep(100)
    assert replay.position == antes
    assert replay.due_in() is None
    assert replay.pop_due() == []
    replay.resume()
    clock.sleep(1)
    assert replay.position == antes + timedelta(seconds=10)


def test_cambio_de_velocidad_conserva_la_posicion(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=10)
    clock.sleep(2)
    replay.set_speed(60)
    assert replay.position == replay.meta.start + timedelta(seconds=20)
    clock.sleep(1)
    assert replay.position == replay.meta.start + timedelta(seconds=80)


def test_run_en_pausa_espera_sin_emitir(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=None)
    replay.pause()
    corrida = replay.run()
    for _ in range(3):
        clock.sleep(0)  # el bucle solo avanza cuando se le pide el próximo lote
    replay.resume()
    assert next(corrida)[0].event.kind == "driver"


# Seek ------------------------------------------------------------------------------------


def test_seek_adelante_equivale_a_reproducir(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=None)
    replay.seek(ROJA)
    assert replay.state == _plegar(parquet, ROJA)
    assert replay.state.track_status is TrackStatus.SC
    primero = replay.pop_due()
    assert primero[0].event.t == ROJA


def test_seek_atras_y_adelante_da_el_mismo_estado(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=None)
    replay.seek(REANUDACION)
    replay.seek(ROJA - timedelta(minutes=20))
    assert replay.state == _plegar(parquet, ROJA - timedelta(minutes=20))
    replay.seek(ROJA)
    assert replay.state == _plegar(parquet, ROJA)


def test_seek_no_cambia_pausa_ni_velocidad(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=30)
    replay.pause()
    replay.seek(ROJA)
    assert replay.paused
    assert replay.speed == 30
    assert replay.position == ROJA


def test_seek_antes_del_inicio_se_ajusta_al_inicio(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=None)
    replay.seek(ROJA)
    replay.seek(replay.meta.start - timedelta(hours=2))
    assert replay.position == replay.meta.start
    assert replay.state == RaceState()
    assert [p.event.kind for p in replay.pop_due()] == ["driver"] * 22


def test_seek_al_final(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=None)
    replay.seek(datetime(2026, 6, 8, tzinfo=UTC))
    assert replay.finished
    assert replay.state.events_applied == len(read_events(parquet))
    assert list(replay.run()) == []


# Convención de vuelta --------------------------------------------------------------------


def test_seek_lap_deja_el_estado_en_esa_vuelta(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=None)
    replay.seek_lap(61)
    assert replay.state.lap == 61
    assert replay.state.laps_completed == 60
    assert replay.state.track_status is TrackStatus.SC
    # El cruce que abre la vuelta 61: ANT (12) completa la 60 a las 14:20:22.438.
    assert replay.position == datetime(2026, 6, 7, 14, 20, 22, 438000, tzinfo=UTC)
    assert replay.state.cars[12].last_lap is not None
    assert replay.state.cars[12].last_lap.lap == 60
    assert all(paso.lap == 61 for paso in replay.pop_due())


def test_seek_lap_sin_datos(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=None)
    with pytest.raises(ReplayError, match="no hay datos para empezar la vuelta 30"):
        replay.seek_lap(30)  # el recorte de Mónaco tiene las vueltas 57 a 70
    replay.seek_lap(1)
    assert replay.position == replay.meta.start


def test_vuelta_coincide_con_los_mensajes_de_safety_car(parquet: Path, clock: FakeClock) -> None:
    """La vuelta en curso del replay es la misma que la FIA pone en sus mensajes de SC."""
    replay = Replay.from_parquet(parquet, clock, speed=None)
    replay.seek_lap(58)
    vistos: list[tuple[str, int, int]] = []
    for paso in _pasos(replay):
        e = paso.event
        if isinstance(e, RaceControlMessage) and e.category == "SafetyCar":
            assert e.lap is not None
            vistos.append((e.message, e.lap, paso.lap))
    assert vistos == [
        ("SAFETY CAR DEPLOYED", 60, 60),
        ("SAFETY CAR IN THIS LAP", 65, 65),
        ("SAFETY CAR DEPLOYED", 66, 66),
    ]


def test_cambios_de_estado_de_pista_por_vuelta(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=None)
    replay.seek_lap(58)
    cambios = [
        (paso.event.status, paso.lap)
        for paso in _pasos(replay)
        if isinstance(paso.event, TrackStatusChanged)
    ]
    assert cambios == [
        (TrackStatus.SC, 60),
        (TrackStatus.SC_ENDING, 65),
        (TrackStatus.GREEN, 65),
        (TrackStatus.SC, 66),
        (TrackStatus.RED, 68),
        (TrackStatus.GREEN, 68),
    ]


def test_lider_es_el_piloto_en_p1_en_sao_paulo(sao_paulo: Path, clock: FakeClock) -> None:
    # El recorte de Mónaco no trae eventos de P1 (OpenF1 publica la posición solo al cambiar y
    # ANT lidera desde antes del tramo), por eso el líder se prueba con São Paulo.
    replay = Replay.from_parquet(sao_paulo, clock, speed=None)
    replay.seek(datetime(2026, 11, 9, tzinfo=UTC))
    assert replay.state.leader == 1
    assert replay.state.acronym(1) == "NOR"


def _t(segundos: float) -> datetime:
    return datetime(2026, 6, 7, 13, 0, tzinfo=UTC) + timedelta(seconds=segundos)


def test_lider_y_numero_de_vuelta_salen_de_fuentes_distintas() -> None:
    """El nombre sale de P1; el número, del máximo de vueltas completadas por cualquier auto."""
    estado = RaceState()
    estado.apply(PositionChanged(t=_t(0), driver=1, position=1))
    estado.apply(PositionChanged(t=_t(0), driver=44, position=2))
    estado.apply(LapCompleted(t=_t(90), driver=1, lap=10))
    assert (estado.lap, estado.leader) == (11, 1)
    # 44 completa la 11 antes que 1 (que perdió tiempo) pero todavía figura P2.
    estado.apply(LapCompleted(t=_t(170), driver=44, lap=11))
    assert (estado.lap, estado.leader) == (12, 1)
    # La nueva posición desplaza al que la tenía hasta que llegue su propio evento.
    estado.apply(PositionChanged(t=_t(171), driver=44, position=1))
    assert estado.leader == 44
    assert estado.cars[1].position is None
    assert estado.acronym(44) == "#44"  # sin evento driver, el número


def test_final_lap_queda_fija_en_la_bandera_a_cuadros() -> None:
    inicio = datetime(2026, 6, 7, 13, 0, tzinfo=UTC)
    estado = RaceState()
    estado.laps_completed = 77
    estado.apply(
        TrackStatusChanged(t=inicio, status=TrackStatus.FINISHED, lap=78, cause="CHEQUERED FLAG")
    )
    estado.laps_completed = 78
    assert estado.lap == 78


# Paradas ---------------------------------------------------------------------------------


def test_paradas_bajo_sc_en_monaco(parquet: Path, clock: FakeClock) -> None:
    replay = Replay.from_parquet(parquet, clock, speed=None)
    replay.seek(datetime(2026, 6, 7, 14, 25, tzinfo=UTC))
    paradas = {replay.state.acronym(n) for n, a in replay.state.cars.items() if a.stops}
    assert paradas == {"HAM", "ALO", "RUS", "PER", "BOR"}
    assert sum(a.lane_passes for a in replay.state.cars.values()) > 0


def test_paradas_normales_de_sao_paulo_traen_detencion(sao_paulo: Path, clock: FakeClock) -> None:
    pits = read_events(sao_paulo, kinds=["pit"])
    assert pits
    assert all(isinstance(p, PitLane) and p.stationary_s is not None for p in pits)
    replay = Replay.from_parquet(sao_paulo, clock, speed=None)
    replay.seek(datetime(2026, 11, 9, tzinfo=UTC))
    assert sum(a.stops for a in replay.state.cars.values()) == len(pits)


# CLI -------------------------------------------------------------------------------------


def test_cli_replay_sin_espera(
    parquet: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("time.sleep", _prohibido)
    datos = parquet.parent.parent
    assert main(["replay", "2026-monaco-r", "--no-wait", "--data-dir", str(datos)]) == 0
    salida = capsys.readouterr().out
    assert "2026-monaco-r · Mónaco · openf1 · sin espera · hora UTC" in salida
    # Sin eventos de P1 en el recorte, el marcador no nombra líder.
    assert "── Vuelta 60 · lidera ---" in salida
    assert "14:20:02  v60  DIRECCIÓN  SAFETY CAR DEPLOYED" in salida
    assert "14:20:02  v60  PISTA      SC (SAFETY CAR DEPLOYED)" in salida
    assert "v68  PISTA      RED" in salida
    assert "14:21:26  v61  PARADA     HAM 8,6 s detenido" in salida
    assert "  PIT LANE   " not in salida  # pasadas sin detención: solo con --verbose
    assert "Fin del replay:" in salida


def test_cli_replay_desde_vuelta_y_verbose(
    parquet: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    datos = str(parquet.parent.parent)
    argv = ["replay", "2026-monaco-r", "--no-wait", "--from-lap", "66", "--verbose"]
    assert main([*argv, "--data-dir", datos]) == 0
    salida = capsys.readouterr().out
    assert salida.splitlines()[1] == "── Vuelta 66 · lidera ---"
    assert "SAFETY CAR DEPLOYED" in salida  # el segundo SC, en la 66
    assert "14:20:02" not in salida
    assert "POSICIÓN" in salida
    assert "CLIMA" in salida


def test_cli_replay_sin_canonico(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["replay", "2026-monaco-r", "--no-wait", "--data-dir", str(tmp_path)]) == 1
    assert "correr make normalize SESSION=2026-monaco-r" in capsys.readouterr().err


def test_cli_replay_velocidad_invalida(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["replay", "2026-monaco-r", "--speed", "0"])
    assert "mayor que 0" in capsys.readouterr().err


def _prohibido(_segundos: float) -> None:
    raise AssertionError("el modo sin espera no duerme")


def test_meta_de_monaco(parquet: Path) -> None:
    meta: SessionMeta = read_meta(parquet)
    assert meta.start == datetime(2026, 6, 7, 13, 0, tzinfo=UTC)
