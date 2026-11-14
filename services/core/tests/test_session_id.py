"""Tests del identificador de sesión y de la tabla de circuitos."""

from __future__ import annotations

import pytest

from apexpulse.session_id import SESSION_TYPES, SessionId, SessionIdError, circuits


def test_parse_carrera_sao_paulo() -> None:
    sesion = SessionId.parse("2026-sao-paulo-r")
    assert (sesion.year, sesion.circuit, sesion.kind) == (2026, "sao-paulo", "r")
    assert str(sesion) == "2026-sao-paulo-r"
    assert sesion.circuit_info.openf1 == "Interlagos"


def test_parse_circuito_con_varias_palabras_y_tipo_largo() -> None:
    sesion = SessionId.parse("2025-abu-dabi-fp1")
    assert sesion.circuit == "abu-dabi"
    assert sesion.kind == "fp1"


@pytest.mark.parametrize(
    ("texto", "mensaje"),
    [
        ("sao-paulo-2026", "no es un identificador válido"),
        ("2026-Sao-Paulo-r", "no es un identificador válido"),
        ("2022-sao-paulo-r", "desde 2023"),
        ("2026-sao-paulo-race", "tipo 'race' desconocido"),
        ("2026-interlagos-r", "circuito 'interlagos' desconocido"),
    ],
)
def test_parse_invalido(texto: str, mensaje: str) -> None:
    with pytest.raises(SessionIdError, match=mensaje):
        SessionId.parse(texto)


def test_tabla_de_circuitos() -> None:
    tabla = circuits()
    assert len(tabla) == 25
    for slug, circuito in tabla.items():
        assert circuito.slug == slug
        assert circuito.nombre and circuito.openf1
    assert "Sprint Shootout" in SESSION_TYPES["sq"]
