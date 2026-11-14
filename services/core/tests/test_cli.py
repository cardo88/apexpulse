"""Tests de la línea de comandos (sin red: solo caminos que no llegan a la fuente)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apexpulse.cli import main
from apexpulse.sources.openf1 import ENDPOINTS
from apexpulse.sources.rawstore import write_jsonl_zst


def test_identificador_invalido(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["fetch", "2026-interlagos-r", "--data-dir", str(tmp_path)]) == 1
    assert "circuito 'interlagos' desconocido" in capsys.readouterr().err


def test_fetch_desde_cache(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    destino = tmp_path / "raw" / "2026" / "2026-sao-paulo-r" / "openf1"
    endpoints = {}
    for endpoint in ENDPOINTS:
        write_jsonl_zst(destino / f"{endpoint}.jsonl.zst", [{"session_key": 11412}])
        endpoints[endpoint] = {"file": f"{endpoint}.jsonl.zst", "rows": 1}
    manifiesto = {"openf1_session": {"session_key": 11412}, "endpoints": endpoints}
    (destino / "manifest.json").write_text(json.dumps(manifiesto), encoding="utf-8")

    assert main(["fetch", "2026-sao-paulo-r", "--data-dir", str(tmp_path)]) == 0
    salida = capsys.readouterr().out
    assert "session_key 11412): caché local, 0 requests" in salida
    assert "laps                1 registros" in salida
