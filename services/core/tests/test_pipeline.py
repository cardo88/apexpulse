"""Pipeline completo desde los fixtures: dos corridas independientes dan salida idéntica.

Cada corrida parte de cero en su propio directorio: baja el fixture con el adaptador (OpenF1
simulado), normaliza, escribe el Parquet canónico, reproduce con el motor de lecturas y vuelve a
reproducir por la CLI. Se compara todo: avisos, bytes del Parquet, lecturas, consola y la salida
de `python -m apexpulse replay`. Es la garantía de determinismo de AGENTS.md ("misma entrada,
misma salida") sobre el camino entero, no solo sobre el motor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apexpulse.cli import main
from helpers import FIXTURES_POR_SESION, Corrida, correr_pipeline, lecturas_a_json


def _salida_de_la_cli(trabajo: Path, sesion: str, capsys: pytest.CaptureFixture[str]) -> str:
    assert main(["replay", sesion, "--no-wait", "--data-dir", str(trabajo)]) == 0
    return capsys.readouterr().out


@pytest.mark.parametrize("sesion", list(FIXTURES_POR_SESION))
def test_dos_corridas_desde_los_fixtures_dan_la_misma_salida(
    sesion: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    primera = correr_pipeline(sesion, tmp_path / "a")
    segunda = correr_pipeline(sesion, tmp_path / "b")

    assert primera.warnings == segunda.warnings
    assert primera.parquet_sha256 == segunda.parquet_sha256
    assert primera.readings == segunda.readings
    assert lecturas_a_json(primera.readings) == lecturas_a_json(segunda.readings)
    assert primera.console == segunda.console
    assert _salida_de_la_cli(tmp_path / "a", sesion, capsys) == _salida_de_la_cli(
        tmp_path / "b", sesion, capsys
    )


@pytest.mark.parametrize("sesion", list(FIXTURES_POR_SESION))
def test_cada_fixture_produce_las_lecturas_de_las_reglas_que_ejercita(
    sesion: str, tmp_path: Path
) -> None:
    """Cada carrera ejercita lo que dice su README: no hay corrida vacía por un error de camino."""
    corrida: Corrida = correr_pipeline(sesion, tmp_path)
    reglas = {r.rule for r in corrida.readings}
    esperadas = {
        "2026-monaco-r": {"cheap_stop"},
        "2026-australia-r": {"cheap_stop", "undercut_window"},
        "2026-sao-paulo-r": {"undercut_window"},
    }
    assert reglas == esperadas[sesion]
    assert any("LECTURA" in linea for linea in corrida.console)
