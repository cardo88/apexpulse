"""Tests de `calibracion.py`: categorización de intentos de undercut y las tablas de reporte."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from apexpulse.calibracion import (
    Categoria,
    Intento,
    analizar_sesion,
    celda,
    cumple_regla,
    resumen_categorias,
    sensibilidad_no_respondio,
    tabla_acumulada_edad,
    tabla_acumulada_gap,
    tabla_diferencia_edad,
    tabla_disjunta_gap,
    wilson,
)
from apexpulse.model import (
    Compound,
    Event,
    IntervalUpdated,
    LapCompleted,
    PitLane,
    PositionChanged,
    SessionMeta,
    StintStarted,
    write_events,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
P, R = 1, 2  # perseguidor, rival


def _t(segundos: float) -> datetime:
    return T0 + timedelta(seconds=segundos)


def _sesion(tmp_path: Path, eventos: list[Event], nombre: str = "test") -> Path:
    destino = tmp_path / f"{nombre}.parquet"
    meta = SessionMeta(session=nombre, source="test", circuit="Test", start=T0, end=_t(10_000))
    write_events(destino, meta, eventos)
    return destino


def _base(*, p_pit_lap: int = 9, swap_posicion: bool = False) -> list[Event]:
    """P y R arrancan juntos (R primero); P para en `p_pit_lap`, sin que R haya parado antes."""
    eventos: list[Event] = [
        StintStarted(t=_t(0), driver=P, lap=1, stint=1, compound=Compound.SOFT, tyre_age=0),
        StintStarted(t=_t(0), driver=R, lap=1, stint=1, compound=Compound.SOFT, tyre_age=0),
        PositionChanged(t=_t(0), driver=R, position=1),
        PositionChanged(t=_t(1), driver=P, position=2),
        IntervalUpdated(t=_t(2), driver=P, interval_s=1.0),
    ]
    for lap in range(1, p_pit_lap):
        eventos.append(LapCompleted(t=_t(10 * lap), driver=P, lap=lap, lap_time_s=10.0))
        eventos.append(LapCompleted(t=_t(10 * lap + 3), driver=R, lap=lap, lap_time_s=10.0))
    eventos.append(
        PitLane(t=_t(10 * p_pit_lap), driver=P, lap=p_pit_lap, lane_s=20.0, stationary_s=3.0)
    )
    eventos.append(
        StintStarted(
            t=_t(10 * p_pit_lap),
            driver=P,
            lap=p_pit_lap + 1,
            stint=2,
            compound=Compound.MEDIUM,
            tyre_age=0,
        )
    )
    eventos.append(
        LapCompleted(t=_t(10 * p_pit_lap + 10), driver=P, lap=p_pit_lap + 1, lap_time_s=10.0)
    )
    if swap_posicion:
        eventos.append(PositionChanged(t=_t(10 * p_pit_lap + 5), driver=P, position=1))
        eventos.append(PositionChanged(t=_t(10 * p_pit_lap + 5), driver=R, position=2))
    return eventos


def _parada_r(lap: int, *, nuevo_stint_lap: int | None = None) -> list[Event]:
    nuevo_stint_lap = nuevo_stint_lap or lap + 1
    return [
        LapCompleted(t=_t(10 * lap + 3), driver=R, lap=lap, lap_time_s=10.0),
        PitLane(t=_t(10 * lap + 3), driver=R, lap=lap, lane_s=20.0, stationary_s=3.0),
        StintStarted(
            t=_t(10 * lap + 3),
            driver=R,
            lap=nuevo_stint_lap,
            stint=2,
            compound=Compound.MEDIUM,
            tyre_age=0,
        ),
        LapCompleted(
            t=_t(10 * nuevo_stint_lap + 3), driver=R, lap=nuevo_stint_lap, lap_time_s=10.0
        ),
    ]


def _intentos_de_p(tmp_path: Path, eventos: list[Event], *, k: int = 5) -> list[Intento]:
    """Intentos cuyo perseguidor es P: `tracker.stops` también trae los de R, si paró."""
    parquet = _sesion(tmp_path, eventos)
    return [i for i in analizar_sesion(parquet, k=k) if i.perseguidor == P]


def _un_intento(tmp_path: Path, eventos: list[Event], *, k: int = 5) -> Intento:
    (intento,) = _intentos_de_p(tmp_path, eventos, k=k)
    return intento


def test_escalado_exito_si_p_queda_adelante(tmp_path: Path) -> None:
    eventos = _base(p_pit_lap=9, swap_posicion=True) + _parada_r(11)
    intento = _un_intento(tmp_path, eventos)
    assert intento.categoria is Categoria.ESCALADO
    assert intento.exito is True
    assert intento.gap_previo == 1.0


def test_escalado_fracaso_si_p_no_pasa(tmp_path: Path) -> None:
    eventos = _base(p_pit_lap=9, swap_posicion=False) + _parada_r(11)
    intento = _un_intento(tmp_path, eventos)
    assert intento.categoria is Categoria.ESCALADO
    assert intento.exito is False


def test_ya_habia_parado_si_r_paro_antes(tmp_path: Path) -> None:
    eventos = _parada_r(4) + _base(p_pit_lap=9, swap_posicion=True)
    intento = _un_intento(tmp_path, eventos)
    assert intento.categoria is Categoria.YA_HABIA_PARADO
    assert intento.exito is None


def test_no_respondio_en_k_si_r_para_mucho_despues(tmp_path: Path) -> None:
    eventos = _base(p_pit_lap=9, swap_posicion=True) + _parada_r(20)
    intento = _un_intento(tmp_path, eventos)
    assert intento.categoria is Categoria.NO_RESPONDIO_EN_K
    assert intento.exito is None
    assert intento.exito_horizonte is True  # al horizonte Lp+K, P ya está adelante (swap en t+5)


def test_no_respondio_en_k_si_r_nunca_para(tmp_path: Path) -> None:
    eventos = _base(p_pit_lap=9, swap_posicion=True)
    # R sigue completando vueltas, nunca vuelve a parar.
    for lap in range(9, 20):
        eventos.append(LapCompleted(t=_t(10 * lap + 3), driver=R, lap=lap, lap_time_s=10.0))
    intento = _un_intento(tmp_path, eventos)
    assert intento.categoria is Categoria.NO_RESPONDIO_EN_K
    assert intento.exito_horizonte is True


def test_sin_rival_comparable_si_p_es_lider(tmp_path: Path) -> None:
    eventos: list[Event] = [
        StintStarted(t=_t(0), driver=P, lap=1, stint=1, compound=Compound.SOFT, tyre_age=0),
        PositionChanged(t=_t(0), driver=P, position=1),
    ]
    for lap in range(1, 9):
        eventos.append(LapCompleted(t=_t(10 * lap), driver=P, lap=lap, lap_time_s=10.0))
    eventos.append(PitLane(t=_t(90), driver=P, lap=9, lane_s=20.0, stationary_s=3.0))
    eventos.append(
        StintStarted(t=_t(90), driver=P, lap=10, stint=2, compound=Compound.MEDIUM, tyre_age=0)
    )
    intento = _un_intento(tmp_path, eventos)
    assert intento.categoria is Categoria.SIN_RIVAL_COMPARABLE
    assert intento.exito is None


def test_dos_paradas_del_mismo_piloto_usan_la_parada_anterior_como_referencia(
    tmp_path: Path,
) -> None:
    """La segunda parada de P no debe verse como "R ya había parado" por la primera parada."""
    eventos = _base(p_pit_lap=9, swap_posicion=True) + _parada_r(11)
    # Segunda parada de P, mucho después; R no vuelve a parar a tiempo esta vez.
    for lap in range(10, 30):
        eventos.append(LapCompleted(t=_t(10 * lap), driver=P, lap=lap, lap_time_s=10.0))
        eventos.append(LapCompleted(t=_t(10 * lap + 3), driver=R, lap=lap, lap_time_s=10.0))
    eventos.append(PitLane(t=_t(300), driver=P, lap=30, lane_s=20.0, stationary_s=3.0))
    eventos.append(
        StintStarted(t=_t(300), driver=P, lap=31, stint=3, compound=Compound.HARD, tyre_age=0)
    )
    eventos.append(LapCompleted(t=_t(310), driver=P, lap=31, lap_time_s=10.0))

    intentos = _intentos_de_p(tmp_path, eventos)
    assert len(intentos) == 2
    segunda = intentos[1]
    assert segunda.vuelta_parada == 30
    assert segunda.categoria != Categoria.YA_HABIA_PARADO  # la parada de R en la 11 ya quedó atrás


def test_wilson_contiene_la_proporcion_observada() -> None:
    bajo, alto = wilson(4, 8)
    assert bajo < 0.5 < alto


def test_celda_insuficiente_por_debajo_del_n_minimo() -> None:
    assert celda(3, 5, n_minimo=8).suficiente is False
    assert celda(6, 8, n_minimo=8).suficiente is True


def _intento_escalado(gap: float, edad_p: int, edad_r: int, exito: bool) -> Intento:
    return Intento("s", P, R, 10, Categoria.ESCALADO, gap, edad_p, edad_r, exito=exito)


def test_tabla_acumulada_gap_el_candidato_crece_y_el_complemento_decrece_en_n() -> None:
    intentos = [
        _intento_escalado(0.5, 10, 10, True),
        _intento_escalado(1.8, 10, 10, False),
        _intento_escalado(2.8, 10, 10, False),
    ]
    tabla = tabla_acumulada_gap(intentos, (1.0, 2.0, 3.0), n_minimo=1)
    dentro_1, fuera_1 = tabla[1.0]
    dentro_2, fuera_2 = tabla[2.0]
    dentro_3, fuera_3 = tabla[3.0]
    assert (dentro_1.n, fuera_1.n) == (1, 2)
    assert (dentro_2.n, fuera_2.n) == (2, 1)
    assert (dentro_3.n, fuera_3.n) == (3, 0)  # nada queda afuera: complemento vacío


def test_tabla_acumulada_edad_filtra_mayor_o_igual() -> None:
    intentos = [
        _intento_escalado(1.0, 3, 3, True),
        _intento_escalado(1.0, 12, 3, False),
    ]
    tabla = tabla_acumulada_edad(intentos, (5, 10), n_minimo=1)
    dentro_5, fuera_5 = tabla[5]
    dentro_10, fuera_10 = tabla[10]
    assert (dentro_5.n, fuera_5.n) == (1, 1)
    assert (dentro_10.n, fuera_10.n) == (1, 1)


def test_tabla_disjunta_gap_no_se_superpone() -> None:
    intentos = [_intento_escalado(0.5, 10, 10, True), _intento_escalado(1.5, 10, 10, True)]
    tabla = tabla_disjunta_gap(intentos, ((0.0, 1.0), (1.0, 2.0)), n_minimo=1)
    assert tabla[(0.0, 1.0)].n == 1
    assert tabla[(1.0, 2.0)].n == 1


def test_tabla_diferencia_edad_sin_filtro_no_tiene_complemento() -> None:
    intentos = [_intento_escalado(1.0, 10, 10, True), _intento_escalado(1.0, 15, 5, False)]
    tabla = tabla_diferencia_edad(intentos, (0, 5), n_minimo=1)
    dentro_0, fuera_0 = tabla[0]
    dentro_5, fuera_5 = tabla[5]
    assert dentro_0.n == 2
    assert fuera_0.n == 0
    assert dentro_5.n == 1  # solo el segundo tiene |10| de diferencia
    assert fuera_5.n == 1


def test_resumen_categorias() -> None:
    intentos = [
        _intento_escalado(1.0, 10, 10, True),
        Intento("s", P, R, 1, Categoria.YA_HABIA_PARADO),
        Intento("s", P, R, 2, Categoria.SIN_RIVAL_COMPARABLE),
    ]
    resumen = resumen_categorias(intentos)
    assert resumen[Categoria.YA_HABIA_PARADO] == 1
    assert resumen[Categoria.SIN_RIVAL_COMPARABLE] == 1


def test_cumple_regla_exige_n_suficiente_y_wilson_fuera_de_la_base() -> None:
    candidato = celda(7, 10, n_minimo=8)  # 70%, Wilson no toca valores muy bajos
    complemento_bajo = celda(1, 10, n_minimo=8)  # 10%, claramente afuera del Wilson del candidato
    complemento_insuficiente = celda(1, 3, n_minimo=8)
    assert cumple_regla(candidato, complemento_bajo) is True
    assert cumple_regla(candidato, complemento_insuficiente) is False
    assert cumple_regla(complemento_insuficiente, candidato) is False


def test_sensibilidad_no_respondio_cambia_n_y_puede_cambiar_la_tasa() -> None:
    intentos = [
        _intento_escalado(1.0, 10, 10, True),
        Intento("s", P, R, 1, Categoria.NO_RESPONDIO_EN_K, exito_horizonte=False),
    ]
    sin, con = sensibilidad_no_respondio(intentos, n_minimo=1)
    assert sin.n == 1
    assert con.n == 2
    assert con.aciertos == 1
