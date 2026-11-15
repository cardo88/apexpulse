"""Tests del motor de lecturas: paradas reales, `cheap_stop`, `undercut_window` y causalidad.

Dos niveles: eventos sintéticos para cada rama de las reglas, y las carreras reales grabadas
(Mónaco con SC, São Paulo sin neutralizaciones y Australia con tres VSC) para los casos que
importan. Los reproductores usan `FakeClock`: no hay esperas reales.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from apexpulse.cli import main
from apexpulse.model import (
    Compound,
    DriverInfo,
    Event,
    IntervalUpdated,
    LapCompleted,
    PitLane,
    PositionChanged,
    StintStarted,
    TrackStatus,
    TrackStatusChanged,
    read_events,
    write_events,
)
from apexpulse.readings import (
    ConfigError,
    Engine,
    Reading,
    load_config,
    load_messages,
)
from apexpulse.readings.stops import juego_distinto
from apexpulse.replay import FakeClock, RaceState, Replay
from conftest import (
    OPENF1_AUSTRALIA,
    OPENF1_MONACO,
    OPENF1_SAO_PAULO,
    OPENF1_SAO_PAULO_PARADAS,
    normalizar_fixture,
)

T0 = datetime(2026, 6, 7, 13, 0, tzinfo=UTC)


def _t(segundos: float) -> datetime:
    return T0 + timedelta(seconds=segundos)


# Mesa sintética --------------------------------------------------------------------------------


class Mesa:
    """Un `RaceState` y un `Engine` alimentados evento por evento, como hace el replay."""

    def __init__(self, engine: Engine | None = None) -> None:
        self.state = RaceState()
        self.engine = Engine.default() if engine is None else engine
        self.lecturas: list[Reading] = []

    def feed(self, *eventos: Event) -> list[Reading]:
        nuevas: list[Reading] = []
        for evento in eventos:
            self.state.apply(evento)
            nuevas += self.engine.process(evento, self.state)
        self.lecturas += nuevas
        return nuevas


def _piloto(numero: int, codigo: str) -> DriverInfo:
    return DriverInfo(t=_t(0), driver=numero, acronym=codigo, name=f"Piloto {codigo}")


def _stint(
    s: float,
    driver: int,
    n: int,
    lap: int,
    compound: Compound = Compound.MEDIUM,
    age: int = 0,
) -> StintStarted:
    return StintStarted(t=_t(s), driver=driver, stint=n, lap=lap, compound=compound, tyre_age=age)


def _pit(
    s: float, driver: int, lap: int, stationary: float | None = None, lane: float | None = 24.0
) -> PitLane:
    return PitLane(t=_t(s), driver=driver, lap=lap, lane_s=lane, stationary_s=stationary)


def _vuelta(s: float, driver: int, lap: int, *, pit_out: bool = False) -> LapCompleted:
    return LapCompleted(t=_t(s), driver=driver, lap=lap, lap_time_s=90.0, pit_out=pit_out)


def _estado(s: float, status: TrackStatus, lap: int = 5) -> TrackStatusChanged:
    return TrackStatusChanged(t=_t(s), status=status, lap=lap, cause="test")


def _mesa_con_dos() -> Mesa:
    mesa = Mesa()
    mesa.feed(_piloto(1, "HAM"), _piloto(2, "ANT"), _stint(0, 1, 1, 1), _stint(0, 2, 1, 1))
    return mesa


# juego_distinto --------------------------------------------------------------------------------


def _distinto(**kw: object) -> bool:
    base: dict[str, object] = {
        "compuesto_anterior": Compound.MEDIUM,
        "edad_anterior": 0,
        "vuelta_anterior": 1,
        "compuesto": Compound.MEDIUM,
        "edad": 0,
        "vuelta": 20,
    }
    return juego_distinto(**{**base, **kw})  # type: ignore[arg-type]


def test_juego_distinto_por_compuesto() -> None:
    assert _distinto(compuesto=Compound.HARD, edad=19)


def test_mismo_juego_llega_con_la_edad_esperada() -> None:
    # HAM en Mónaco: stint 3 en la vuelta 60 con 4 vueltas de uso, stint 4 en la 61 con 5.
    assert not _distinto(edad_anterior=4, vuelta_anterior=60, vuelta=61, edad=5)


def test_mismo_compuesto_con_menos_edad_es_juego_nuevo() -> None:
    assert _distinto(edad_anterior=4, vuelta_anterior=60, vuelta=61, edad=0)
    assert _distinto(edad_anterior=10, vuelta_anterior=66, vuelta=68, edad=4)  # HAM bajo roja


def test_sin_edad_decide_solo_el_compuesto() -> None:
    assert _distinto(edad=None, compuesto=Compound.HARD)
    assert not _distinto(edad=None)
    assert not _distinto(edad_anterior=None)
    assert _distinto(edad_anterior=None, compuesto=Compound.SOFT)


def test_compuesto_desconocido_no_alcanza_para_decidir() -> None:
    # Con UNKNOWN no se compara el compuesto: decide la edad (esperada: 19 + 19 = 38).
    assert not _distinto(compuesto=Compound.UNKNOWN, edad_anterior=19, vuelta_anterior=1, edad=38)
    assert _distinto(compuesto=Compound.UNKNOWN, edad_anterior=19, vuelta_anterior=1, edad=0)


def test_sin_stint_anterior_solo_cuenta_el_juego_sin_uso() -> None:
    assert _distinto(compuesto_anterior=None, vuelta_anterior=None, edad=0)
    assert not _distinto(compuesto_anterior=None, vuelta_anterior=None, edad=7)
    assert not _distinto(compuesto_anterior=None, vuelta_anterior=None, edad=None)


# Paradas reales y cheap_stop (sintético) -------------------------------------------------------


def test_con_detencion_se_emite_en_el_momento_sin_esperar_el_stint() -> None:
    mesa = _mesa_con_dos()
    mesa.feed(_estado(50, TrackStatus.SC))
    (lectura,) = mesa.feed(_pit(100, 1, 10, stationary=2.5, lane=24.0))
    assert lectura.key == "cheap_stop:1:10"
    assert (
        lectura.text
        == "HAM para bajo Safety Car en la vuelta 1: 2,5 s detenido y 24,0 s en pit lane."
    )
    assert lectura.t == _t(100)
    assert lectura.evidence_value("criterio") == "detencion"
    assert lectura.evidence_value("instante_pasada") == lectura.evidence_value(
        "instante_confirmacion"
    )


def test_sin_detencion_se_difiere_hasta_el_stint_de_la_vuelta_siguiente() -> None:
    mesa = _mesa_con_dos()
    mesa.feed(_estado(50, TrackStatus.SC))
    assert mesa.feed(_pit(100, 1, 10)) == []  # todavía no se sabe si cambió neumáticos
    assert mesa.feed(_vuelta(110, 1, 10)) == []
    (lectura,) = mesa.feed(_stint(110, 1, 2, 11, Compound.HARD))
    assert lectura.key == "cheap_stop:1:10"  # la vuelta de la pasada, no la de la confirmación
    assert lectura.t == _t(110)
    assert lectura.evidence_value("instante_pasada") == _t(100).isoformat()
    assert lectura.evidence_value("instante_confirmacion") == _t(110).isoformat()
    assert lectura.evidence_value("criterio") == "stint"
    assert lectura.text == (
        "HAM cambia neumáticos bajo Safety Car en la vuelta 1: duros con 0 vueltas de uso"
        " y 24,0 s en pit lane."
    )


def test_stint_que_llego_antes_que_la_pasada_confirma_en_el_momento() -> None:
    mesa = _mesa_con_dos()
    mesa.feed(_estado(50, TrackStatus.SC), _stint(90, 1, 2, 10, Compound.SOFT))
    (lectura,) = mesa.feed(_pit(100, 1, 10))  # Mónaco: el stint abre en la vuelta de la pasada
    assert lectura.evidence_value("instante_pasada") == lectura.evidence_value(
        "instante_confirmacion"
    )


def test_stint_partido_con_el_mismo_juego_no_es_una_parada() -> None:
    mesa = _mesa_con_dos()
    mesa.feed(_stint(90, 1, 2, 60, Compound.SOFT, age=4), _estado(95, TrackStatus.SC))
    mesa.feed(_pit(100, 1, 61))
    # HAM bajo SC: el stint 3 sigue con el mismo juego (edad esperada exacta).
    assert mesa.feed(_stint(100, 1, 3, 61, Compound.SOFT, age=5)) == []
    assert mesa.engine.tracker.stops == {}


def test_la_confirmacion_diferida_vence_sin_emitir() -> None:
    mesa = _mesa_con_dos()
    mesa.feed(_estado(50, TrackStatus.SC), _pit(100, 1, 10))
    assert mesa.feed(_vuelta(110, 1, 10), _vuelta(200, 1, 11)) == []
    assert mesa.engine.tracker.expired == 0
    assert mesa.feed(_vuelta(290, 1, 12)) == []  # pasada + 2 sin StintStarted
    assert mesa.engine.tracker.expired == 1
    assert mesa.feed(_stint(300, 1, 2, 13, Compound.HARD)) == []  # llegó tarde: no confirma
    assert mesa.engine.tracker.stops == {}


def test_primer_stint_no_es_un_cambio() -> None:
    mesa = _mesa_con_dos()
    mesa.feed(_estado(50, TrackStatus.SC))
    assert mesa.feed(_pit(60, 1, 1)) == []
    assert mesa.engine.tracker.stops == {}


def test_bajo_verde_se_registra_la_parada_pero_no_hay_lectura() -> None:
    mesa = _mesa_con_dos()
    assert mesa.feed(_pit(100, 1, 10, stationary=2.4)) == []
    assert [p.pit_lap for p in mesa.engine.tracker.stops[1]] == [10]


def test_bajo_bandera_roja_no_dispara() -> None:
    mesa = _mesa_con_dos()
    mesa.feed(_estado(50, TrackStatus.RED))
    assert mesa.feed(_pit(100, 1, 10, stationary=30.0)) == []


def test_sc_y_su_final_cuentan_como_neutralizacion() -> None:
    for estado in (TrackStatus.SC, TrackStatus.SC_ENDING):
        mesa = _mesa_con_dos()
        mesa.feed(_estado(50, estado))
        (lectura,) = mesa.feed(_pit(100, 1, 10, stationary=2.5))
        assert "bajo Safety Car " in lectura.text


def test_vsc_cuenta_pero_vsc_ending_no() -> None:
    mesa = _mesa_con_dos()
    mesa.feed(_estado(50, TrackStatus.VSC))
    (lectura,) = mesa.feed(_pit(100, 1, 10, stationary=2.5))
    assert "bajo VSC " in lectura.text

    mesa = _mesa_con_dos()
    mesa.feed(_estado(50, TrackStatus.VSC_ENDING))
    assert mesa.feed(_pit(100, 1, 10, stationary=2.5)) == []


def test_key_usa_la_vuelta_propia_y_el_texto_la_del_lider() -> None:
    mesa = _mesa_con_dos()
    mesa.feed(_estado(50, TrackStatus.SC), _vuelta(60, 2, 20))  # el líder va por la vuelta 21
    (lectura,) = mesa.feed(_pit(100, 1, 18, stationary=3.0))  # HAM, doblado, en su vuelta 18
    assert lectura.key == "cheap_stop:1:18"
    assert lectura.lap == 21
    assert "en la vuelta 21" in lectura.text


def test_los_textos_no_afirman_ahorro() -> None:
    mesa = _mesa_con_dos()
    mesa.feed(_estado(50, TrackStatus.SC))
    textos = [m.text for m in mesa.feed(_pit(100, 1, 10, stationary=2.5))]
    plantillas = load_messages().templates
    textos += [t for regla in plantillas.values() for t in regla.values()]
    assert textos
    for texto in textos:
        for palabra in ("ahorr", "gana", "barat", "menos tiempo"):
            assert palabra not in texto.lower()


def test_pasada_nueva_reemplaza_a_la_diferida_sin_confirmar() -> None:
    mesa = _mesa_con_dos()
    mesa.feed(_estado(50, TrackStatus.SC), _pit(100, 1, 10))
    assert mesa.feed(_pit(130, 1, 11)) == []
    assert mesa.engine.tracker.expired == 1


# undercut_window (sintético) -------------------------------------------------------------------


def _vuelta_de_los_dos(
    mesa: Mesa,
    lap: int,
    *,
    gap: float | None = 1.2,
    laps_down: int | None = None,
    rival_pit_out: bool = False,
) -> list[Reading]:
    """El auto 1 (perseguidor, P2) y el 2 (rival, P1) completan la vuelta `lap`."""
    s = 100.0 * lap
    return mesa.feed(
        IntervalUpdated(t=_t(s), driver=1, gap_s=gap, interval_s=gap, laps_down=laps_down),
        _vuelta(s + 1, 2, lap, pit_out=rival_pit_out),
        _vuelta(s + 2, 1, lap),
    )


def _carrera_de_dos() -> Mesa:
    mesa = _mesa_con_dos()
    mesa.feed(
        PositionChanged(t=_t(0), driver=2, position=1),
        PositionChanged(t=_t(0), driver=1, position=2),
    )
    return mesa


def _lecturas_de_undercut(mesa: Mesa) -> list[Reading]:
    return [r for r in mesa.lecturas if r.rule == "undercut_window"]


def test_undercut_se_abre_tras_dos_vueltas_con_las_condiciones() -> None:
    mesa = _carrera_de_dos()
    emitidas = [bool(_vuelta_de_los_dos(mesa, n)) for n in range(1, 15)]
    # Con 10 vueltas de uso al completar la 10, la racha de 2 se cumple en la 11.
    assert emitidas.index(True) == 10
    assert sum(emitidas) == 1  # una sola vez por pareja y stint
    (lectura,) = _lecturas_de_undercut(mesa)
    assert lectura.key == "undercut_window:1:2:1"
    assert lectura.drivers == (1, 2)
    assert lectura.evidence_value("gap_s") == 1.2
    assert lectura.evidence_value("edad_perseguidor") == 11
    assert lectura.text == (
        "HAM está a 1,2 s de ANT desde hace 2 vueltas, con neumáticos medios de 11 vueltas"
        " contra medios de 11: ventana de undercut."
    )


def _mesa_con_minimo(minimo: int) -> Mesa:
    datos = _datos(undercut_window__min_lap=minimo)
    mesa = Mesa(Engine(load_config(datos), load_messages()))
    mesa.feed(_piloto(1, "HAM"), _piloto(2, "ANT"), _stint(0, 1, 1, 1), _stint(0, 2, 1, 1))
    mesa.feed(
        PositionChanged(t=_t(0), driver=2, position=1),
        PositionChanged(t=_t(0), driver=1, position=2),
    )
    return mesa


def test_undercut_la_vuelta_minima_retrasa_la_lectura_hasta_cumplir_la_racha() -> None:
    """Con min_lap 20 la racha empieza en la vuelta 20 y se confirma en la 21; no se pierde."""
    mesa = _mesa_con_minimo(20)
    emitidas = [bool(_vuelta_de_los_dos(mesa, n)) for n in range(1, 31)]
    assert emitidas.index(True) == 20  # vuelta 21
    assert sum(emitidas) == 1
    (lectura,) = _lecturas_de_undercut(mesa)
    assert lectura.evidence_value("vuelta_perseguidor") == 21
    assert lectura.evidence_value("vueltas_seguidas") == 2


def test_undercut_la_vuelta_minima_no_cambia_nada_si_ya_se_cumple() -> None:
    con_5 = _carrera_de_dos()
    con_1 = _mesa_con_minimo(1)
    for n in range(1, 15):
        _vuelta_de_los_dos(con_5, n)
        _vuelta_de_los_dos(con_1, n)
    assert con_5.lecturas == con_1.lecturas != []


def test_undercut_ignora_el_intervalo_de_un_auto_doblado() -> None:
    mesa = _carrera_de_dos()
    for n in range(1, 15):
        _vuelta_de_los_dos(mesa, n, gap=None, laps_down=1)
    assert _lecturas_de_undercut(mesa) == []


def test_undercut_ignora_si_el_rival_esta_doblado() -> None:
    mesa = _carrera_de_dos()
    mesa.feed(IntervalUpdated(t=_t(5), driver=2, laps_down=1))
    for n in range(1, 15):
        _vuelta_de_los_dos(mesa, n)
    assert _lecturas_de_undercut(mesa) == []


@pytest.mark.parametrize("gap", [2.1, 5.0])
def test_undercut_exige_gap_de_hasta_dos_segundos(gap: float) -> None:
    mesa = _carrera_de_dos()
    for n in range(1, 15):
        _vuelta_de_los_dos(mesa, n, gap=gap)
    assert _lecturas_de_undercut(mesa) == []


def test_undercut_exige_edad_minima_del_neumatico() -> None:
    mesa = _carrera_de_dos()
    for n in range(1, 10):
        assert _vuelta_de_los_dos(mesa, n) == []  # a la 9 el juego tiene 9 vueltas


def test_undercut_no_evalua_con_el_rival_en_vuelta_de_salida() -> None:
    mesa = _carrera_de_dos()
    for n in range(1, 11):
        _vuelta_de_los_dos(mesa, n)
    # La racha de la 11 se rompe porque el rival completa una vuelta de salida de boxes.
    assert _vuelta_de_los_dos(mesa, 11, rival_pit_out=True) == []
    assert _vuelta_de_los_dos(mesa, 12) == []  # la racha vuelve a empezar
    assert len(_vuelta_de_los_dos(mesa, 13)) == 1


def test_undercut_no_evalua_con_el_perseguidor_en_vuelta_de_entrada() -> None:
    mesa = _carrera_de_dos()
    mesa.feed(_pit(1050, 1, 11))  # HAM pasa por boxes (sin parada confirmada) en su vuelta 11
    for n in range(1, 12):
        assert _vuelta_de_los_dos(mesa, n) == [], n


def test_undercut_espera_tras_una_parada_propia_o_ajena() -> None:
    for piloto in (1, 2):
        mesa = _carrera_de_dos()
        mesa.feed(_pit(850, piloto, 8, stationary=2.6))
        resultados = [bool(_vuelta_de_los_dos(mesa, n)) for n in range(1, 16)]
        # Parada en la vuelta 8: bloquea las vueltas 8, 9 y 10 (recent_stop_laps = 3). Con la edad
        # mínima cumplida en la 10, la racha de 2 vueltas se completa en la 12.
        assert resultados.index(True) == 11, piloto


def test_undercut_solo_con_pista_en_verde() -> None:
    mesa = _carrera_de_dos()
    mesa.feed(_estado(0.5, TrackStatus.SC))
    for n in range(1, 15):
        _vuelta_de_los_dos(mesa, n)
    assert _lecturas_de_undercut(mesa) == []


def test_undercut_reinicia_la_racha_si_cambia_el_rival() -> None:
    mesa = _carrera_de_dos()
    mesa.feed(_piloto(3, "NOR"), _stint(0, 3, 1, 1), _vuelta(999, 3, 10))
    for n in range(1, 11):
        _vuelta_de_los_dos(mesa, n)
    # El auto 3 pasa a ser el rival del 1 antes de la vuelta 11: la racha cuenta desde cero.
    mesa.feed(
        PositionChanged(t=_t(1000), driver=3, position=1),
        PositionChanged(t=_t(1000), driver=1, position=2),
        PositionChanged(t=_t(1000), driver=2, position=3),
    )
    assert _vuelta_de_los_dos(mesa, 11) == []
    (lectura,) = _vuelta_de_los_dos(mesa, 12)
    assert lectura.drivers == (1, 3)


def test_undercut_sin_vuelta_ni_stint_del_rival_no_se_abre() -> None:
    mesa = _carrera_de_dos()
    mesa.feed(_piloto(3, "NOR"))  # el auto 3 todavía no tiene stint ni vueltas
    mesa.feed(
        PositionChanged(t=_t(1), driver=3, position=1),
        PositionChanged(t=_t(1), driver=1, position=2),
        PositionChanged(t=_t(1), driver=2, position=3),
    )
    for n in range(1, 15):
        _vuelta_de_los_dos(mesa, n)
    assert _lecturas_de_undercut(mesa) == []


# Configuración --------------------------------------------------------------------------------


def test_config_empaquetada_esta_marcada_como_no_calibrada() -> None:
    config = load_config()
    assert config.stops.calibrated is False
    assert config.undercut.calibrated is False
    assert (config.undercut.max_gap_s, config.undercut.min_tyre_age_laps) == (2.0, 10)
    assert (config.undercut.confirm_laps, config.undercut.recent_stop_laps) == (2, 3)
    assert config.undercut.min_lap == 5
    assert config.stops.confirm_timeout_laps == 2


def _datos(**cambios: object) -> dict[str, dict[str, object]]:
    datos: dict[str, dict[str, object]] = {
        "stops": {"calibrated": False, "confirm_timeout_laps": 2},
        "undercut_window": {
            "calibrated": False,
            "max_gap_s": 2.0,
            "min_tyre_age_laps": 10,
            "confirm_laps": 2,
            "recent_stop_laps": 3,
            "min_lap": 5,
        },
    }
    for ruta, valor in cambios.items():
        seccion, clave = ruta.split("__")
        datos[seccion][clave] = valor
    return datos


@pytest.mark.parametrize(
    "cambio",
    [
        {"stops__confirm_timeout_laps": 0},
        {"undercut_window__max_gap_s": 0.0},
        {"undercut_window__min_tyre_age_laps": 0},
        {"undercut_window__confirm_laps": 0},
        {"undercut_window__recent_stop_laps": -1},
        {"undercut_window__min_lap": 0},
        {"undercut_window__min_lap": 5.0},
        {"undercut_window__max_gap_s": "2.0"},
    ],
)
def test_config_rechaza_valores_invalidos(cambio: dict[str, object]) -> None:
    with pytest.raises(ConfigError):
        load_config(_datos(**cambio))


def test_config_rechaza_claves_desconocidas_y_secciones_faltantes() -> None:
    datos = _datos()
    datos["undercut_window"]["umbral_nuevo"] = 1
    with pytest.raises(ConfigError, match="desconocidas"):
        load_config(datos)
    with pytest.raises(ConfigError, match="falta la sección"):
        load_config({"stops": datos["stops"]})


def test_mensajes_cubren_todos_los_estados_y_compuestos() -> None:
    mensajes = load_messages()
    assert set(mensajes.compounds) == {c.value for c in Compound}
    with pytest.raises(ConfigError, match="faltan"):
        load_messages({"fragmentos": {}, "estados": {}, "compuestos": {}})


# Carreras reales -------------------------------------------------------------------------------


def _parquet(tmp_path_factory: pytest.TempPathFactory, directorio: Path, session: str) -> Path:
    datos = tmp_path_factory.mktemp(session)
    resultado = normalizar_fixture(directorio, session, datos / "raw")
    destino = datos / "canonical" / f"{session}.parquet"
    write_events(destino, resultado.meta, resultado.events)
    return destino


@pytest.fixture(scope="module")
def monaco(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _parquet(tmp_path_factory, OPENF1_MONACO, "2026-monaco-r")


@pytest.fixture(scope="module")
def australia(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _parquet(tmp_path_factory, OPENF1_AUSTRALIA, "2026-australia-r")


@pytest.fixture(scope="module")
def sao_paulo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _parquet(tmp_path_factory, OPENF1_SAO_PAULO, "2026-sao-paulo-r")


@pytest.fixture(scope="module")
def sao_paulo_paradas(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _parquet(tmp_path_factory, OPENF1_SAO_PAULO_PARADAS, "2026-sao-paulo-r")


def _replay(path: Path) -> Replay:
    return Replay.from_parquet(path, FakeClock(), speed=None, engine=Engine.default())


def _correr(replay: Replay) -> list[Reading]:
    return [lectura for lote in replay.run() for paso in lote for lectura in paso.readings]


def _paradas(replay: Replay) -> set[tuple[str, int]]:
    assert replay.engine is not None
    engine = replay.engine
    assert isinstance(engine, Engine)
    return {
        (replay.state.acronym(d), p.pit_lap) for d, ps in engine.tracker.stops.items() for p in ps
    }


def test_las_5_paradas_de_sao_paulo_sin_stationary_s_son_paradas_reales(
    sao_paulo_paradas: Path,
) -> None:
    sin_detencion = {
        (p.driver, p.lap)
        for p in read_events(sao_paulo_paradas, kinds=["pit"])
        if isinstance(p, PitLane) and p.stationary_s is None
    }
    assert len(sin_detencion) == 5
    replay = _replay(sao_paulo_paradas)
    _correr(replay)
    assert replay.engine is not None and isinstance(replay.engine, Engine)
    reales = {(d, p.pit_lap): p for d, ps in replay.engine.tracker.stops.items() for p in ps}
    nombres = {(replay.state.acronym(d), lap) for d, lap in sin_detencion}
    assert nombres == {("HAD", 16), ("VER", 17), ("ALO", 17), ("COL", 53), ("HAD", 62)}
    for clave in sin_detencion:
        parada = reales[clave]
        assert parada.how == "stint"
        assert parada.confirmed_t >= parada.pass_t  # São Paulo abre el stint al salir
    assert len(reales) == 58  # las 53 con detención y las 5 sin ella
    assert replay.engine.tracker.expired == 0


def test_hul_vuelta_58_en_monaco_no_es_una_parada_real(monaco: Path) -> None:
    pit = next(
        p
        for p in read_events(monaco, kinds=["pit"])
        if isinstance(p, PitLane) and p.lap == 58 and p.stationary_s is None and p.lane_s == 20.5
    )
    replay = _replay(monaco)
    _correr(replay)
    assert replay.state.acronym(pit.driver) == "HUL"
    assert ("HUL", 58) not in _paradas(replay)  # pasada por el pit lane con el mismo juego
    assert replay.engine is not None and isinstance(replay.engine, Engine)
    assert replay.engine.tracker.expired > 0  # la confirmación diferida venció sin emitir


def test_cheap_stop_en_monaco(monaco: Path) -> None:
    replay = _replay(monaco)
    lecturas = _correr(replay)
    cheap = [r for r in lecturas if r.rule == "cheap_stop"]
    con_detencion = {
        (replay.state.acronym(r.drivers[0]), int(r.evidence_value("vuelta_propia")))
        for r in cheap
        if r.evidence_value("criterio") == "detencion"
    }
    # Las 5 paradas con detención bajo el primer SC (vueltas propias: ALO y BOR van doblados).
    assert con_detencion == {("HAM", 60), ("ALO", 58), ("RUS", 60), ("PER", 59), ("BOR", 59)}
    assert {r.evidence_value("estado_de_pista") for r in cheap} <= {"SC", "SC_ENDING"}
    # Ninguna lectura de una pasada con bandera roja (desde las 14:35:06).
    roja = datetime(2026, 6, 7, 14, 35, 6, tzinfo=UTC).isoformat()
    assert all(str(r.evidence_value("instante_pasada")) < roja for r in cheap)
    ham = next(r for r in cheap if r.key == "cheap_stop:44:60")
    assert (
        ham.text == "HAM para bajo Safety Car en la vuelta 61: 8,6 s detenido y 31,2 s en pit lane."
    )


def test_vsc_en_australia_se_deriva_del_texto_de_openf1(australia: Path) -> None:
    estados = read_events(australia, kinds=["track_status"])
    vsc = [e for e in estados if isinstance(e, TrackStatusChanged) and e.status is TrackStatus.VSC]
    assert [(e.cause, e.lap) for e in vsc] == [
        ("VSC DEPLOYED", 12),
        ("VSC DEPLOYED", 18),
        ("VSC DEPLOYED", 34),
    ]


def test_cheap_stop_en_los_tres_vsc_de_australia(australia: Path) -> None:
    replay = _replay(australia)
    lecturas = [r for r in _correr(replay) if r.rule == "cheap_stop"]
    por_vuelta: dict[int, set[str]] = {}
    for r in lecturas:
        assert r.evidence_value("estado_de_pista") == "VSC"  # VSC_ENDING no cuenta
        assert " bajo VSC " in r.text
        por_vuelta.setdefault(r.lap, set()).add(replay.state.acronym(r.drivers[0]))
    por_periodo = {12: 0, 18: 0, 34: 0}
    for vuelta, pilotos in por_vuelta.items():
        periodo = 12 if vuelta <= 14 else 18 if vuelta <= 20 else 34
        por_periodo[periodo] += len(pilotos)
    # v34: negativo limpio. La única pasada del período fue en VSC_ENDING (BOR), que ya no cuenta.
    assert por_periodo == {12: 10, 18: 4, 34: 0}


def test_sin_vsc_ni_sc_no_hay_cheap_stop_en_sao_paulo(sao_paulo_paradas: Path) -> None:
    lecturas = _correr(_replay(sao_paulo_paradas))
    assert [r for r in lecturas if r.rule == "cheap_stop"] == []


# Causalidad y seek -----------------------------------------------------------------------------


def _puntos_de_seek(lecturas: list[Reading]) -> list[datetime]:
    """Cada lectura de una muestra, justo en su instante y un instante después."""
    muestra = lecturas[:: max(1, len(lecturas) // 8)]
    puntos: list[datetime] = []
    for r in muestra:
        puntos += [r.t - timedelta(seconds=1), r.t, r.t + timedelta(microseconds=1)]
    return puntos


@pytest.mark.parametrize("sesion", ["monaco", "australia", "sao_paulo"])
def test_seek_produce_las_mismas_lecturas_que_la_reproduccion_continua(
    sesion: str, request: pytest.FixtureRequest
) -> None:
    path: Path = request.getfixturevalue(sesion)
    continua = _correr(_replay(path))
    assert continua
    assert len({r.key for r in continua}) == len(continua)  # ninguna repetida
    for punto in _puntos_de_seek(continua):
        replay = _replay(path)
        replay.seek(punto)
        assert replay.engine is not None and isinstance(replay.engine, Engine)
        posteriores = _correr(replay)
        # Solo las lecturas de eventos desde el punto de llegada, sin repetir las anteriores.
        assert posteriores == [r for r in continua if r.t >= punto], punto
        assert not {r.key for r in posteriores} & {r.key for r in continua if r.t < punto}
        # El historial incluye también lo que el seek salteó sin emitir.
        assert replay.engine.history == tuple(continua)


@pytest.mark.parametrize("sesion", ["monaco", "australia"])
def test_seek_hacia_atras_reinicia_el_motor(sesion: str, request: pytest.FixtureRequest) -> None:
    path: Path = request.getfixturevalue(sesion)
    continua = _correr(_replay(path))
    replay = _replay(path)
    replay.seek(continua[-1].t + timedelta(seconds=1))  # casi al final
    assert replay.engine is not None and isinstance(replay.engine, Engine)
    assert len(replay.engine.history) == len(continua)
    punto = continua[len(continua) // 2].t
    replay.seek(punto)
    assert replay.engine.history == tuple(r for r in continua if r.t < punto)
    assert _correr(replay) == [r for r in continua if r.t >= punto]


def test_seek_lap_no_repite_lecturas_anteriores(monaco: Path) -> None:
    continua = _correr(_replay(monaco))
    replay = _replay(monaco)
    replay.seek_lap(62)
    inicio = replay.position
    assert _correr(replay) == [r for r in continua if r.t >= inicio]


def test_seek_al_medio_de_una_confirmacion_diferida_la_conserva(
    sao_paulo_paradas: Path,
) -> None:
    """Seek entre la pasada de HAD (v16) y su stint: la lectura de la parada no se pierde."""
    replay = _replay(sao_paulo_paradas)
    replay.seek(datetime(2026, 11, 8, 17, 26, 0, tzinfo=UTC))
    assert replay.engine is not None and isinstance(replay.engine, Engine)
    assert replay.engine.tracker.pending or replay.engine.tracker.stops
    _correr(replay)
    assert any(p.pit_lap == 16 for ps in replay.engine.tracker.stops.values() for p in ps)


def test_dos_ejecuciones_dan_lecturas_identicas(monaco: Path) -> None:
    assert _correr(_replay(monaco)) == _correr(_replay(monaco))


# CLI -------------------------------------------------------------------------------------------


def test_cli_replay_imprime_las_lecturas(monaco: Path, capsys: pytest.CaptureFixture[str]) -> None:
    datos = str(monaco.parent.parent)
    assert main(["replay", "2026-monaco-r", "--no-wait", "--data-dir", datos]) == 0
    salida = capsys.readouterr().out
    assert (
        "14:21:26  v61  LECTURA    HAM para bajo Safety Car en la vuelta 61: 8,6 s detenido"
        " y 31,2 s en pit lane."
    ) in salida
