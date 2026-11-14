"""Tests del crudo en JSONL zstd."""

from __future__ import annotations

from pathlib import Path

from apexpulse.sources.rawstore import read_jsonl_zst, write_jsonl_zst


def test_ida_y_vuelta_conserva_orden_y_acentos(tmp_path: Path) -> None:
    registros = [
        {"session_key": 11412, "location": "São Paulo", "lap_duration": None},
        {"session_key": 11412, "segments": [2048, None, 2051]},
    ]
    destino = tmp_path / "raw" / "laps.jsonl.zst"
    assert write_jsonl_zst(destino, registros) == 2
    assert list(read_jsonl_zst(destino)) == registros
    assert next(iter(read_jsonl_zst(destino))).keys() == registros[0].keys()
    assert not list(destino.parent.glob("*.tmp"))


def test_muchos_registros_cruzan_bloques(tmp_path: Path) -> None:
    registros = [{"i": i, "texto": "x" * 50} for i in range(5000)]
    destino = tmp_path / "intervals.jsonl.zst"
    write_jsonl_zst(destino, registros)
    assert list(read_jsonl_zst(destino)) == registros


def test_lista_vacia(tmp_path: Path) -> None:
    destino = tmp_path / "pit.jsonl.zst"
    assert write_jsonl_zst(destino, []) == 0
    assert list(read_jsonl_zst(destino)) == []
