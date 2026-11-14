"""Escritura y lectura del crudo en JSONL comprimido con zstd (ADR 0005).

Un registro por línea, con las claves en el orden en que llegaron. Las escrituras son
atómicas: se escribe a un temporal y se renombra, así un corte no deja archivos a medias.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import zstandard

NIVEL_ZSTD = 10


def write_jsonl_zst(path: Path, records: Iterable[dict[str, Any]]) -> int:
    """Escribe los registros en `path` y devuelve cuántos escribió."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_name(path.name + ".tmp")
    cantidad = 0
    compresor = zstandard.ZstdCompressor(level=NIVEL_ZSTD)
    with temporal.open("wb") as archivo, compresor.stream_writer(archivo) as salida:
        for registro in records:
            linea = json.dumps(registro, ensure_ascii=False, separators=(",", ":")) + "\n"
            salida.write(linea.encode("utf-8"))
            cantidad += 1
    os.replace(temporal, path)
    return cantidad


def read_jsonl_zst(path: Path) -> Iterator[dict[str, Any]]:
    """Devuelve los registros de `path` en orden."""
    with path.open("rb") as archivo, zstandard.ZstdDecompressor().stream_reader(archivo) as raw:
        pendiente = b""
        while bloque := raw.read(1 << 16):
            pendiente += bloque
            *lineas, pendiente = pendiente.split(b"\n")
            for linea in lineas:
                if linea:
                    yield json.loads(linea)
        if pendiente.strip():
            yield json.loads(pendiente)


def write_json(path: Path, data: Any) -> None:
    """Escribe JSON legible y estable (claves ordenadas), de forma atómica."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_name(path.name + ".tmp")
    texto = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    temporal.write_text(texto + "\n", encoding="utf-8")
    os.replace(temporal, path)
