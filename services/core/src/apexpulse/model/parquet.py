"""Persistencia de los eventos canónicos en Parquet: una tabla ancha por sesión (ADR 0005).

Columnas comunes (`seq`, `t`, `kind`, `driver`, `lap`) más una columna por cada campo de los
tipos de evento; las que no aplican al `kind` de la fila quedan en null. La cabecera
`SessionMeta` viaja en los metadatos del archivo, bajo la clave `apexpulse`.

Misma entrada, mismo archivo: el orden es el de `sort_key` y no se guarda la hora de generación.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from apexpulse.model.events import EVENT_ADAPTER, Event, SessionMeta, sort_key

META_KEY = b"apexpulse"

SCHEMA = pa.schema(
    [
        ("seq", pa.int32()),
        ("t", pa.timestamp("us", tz="UTC")),
        ("kind", pa.string()),
        ("driver", pa.int16()),
        ("lap", pa.int16()),
        # lap
        ("lap_time_s", pa.float64()),
        ("s1_s", pa.float64()),
        ("s2_s", pa.float64()),
        ("s3_s", pa.float64()),
        ("pit_out", pa.bool_()),
        # stint
        ("stint", pa.int16()),
        ("compound", pa.string()),
        ("tyre_age", pa.int16()),
        # pit
        ("lane_s", pa.float64()),
        ("stationary_s", pa.float64()),
        # position
        ("position", pa.int16()),
        # interval
        ("gap_s", pa.float64()),
        ("laps_down", pa.int16()),
        ("interval_s", pa.float64()),
        ("interval_laps", pa.int16()),
        # race_control
        ("category", pa.string()),
        ("message", pa.string()),
        ("flag", pa.string()),
        ("scope", pa.string()),
        ("sector", pa.int16()),
        # track_status
        ("status", pa.string()),
        ("cause", pa.string()),
        # weather
        ("air_c", pa.float64()),
        ("track_c", pa.float64()),
        ("rain", pa.bool_()),
        ("humidity_pct", pa.float64()),
        ("wind_ms", pa.float64()),
        ("wind_deg", pa.int16()),
        ("pressure_hpa", pa.float64()),
    ]
)

_COLUMNAS = tuple(SCHEMA.names)


def to_table(meta: SessionMeta, events: Iterable[Event]) -> pa.Table:
    """Ordena los eventos y arma la tabla con el esquema fijo."""
    ordenados = sorted(events, key=sort_key)
    columnas: dict[str, list[Any]] = {nombre: [] for nombre in _COLUMNAS}
    for seq, evento in enumerate(ordenados):
        fila = evento.model_dump(mode="python")
        desconocidas = fila.keys() - columnas.keys()
        if desconocidas:
            raise ValueError(f"{evento.kind}: campos sin columna: {sorted(desconocidas)}")
        fila["seq"] = seq
        for nombre in _COLUMNAS:
            columnas[nombre].append(fila.get(nombre))
    metadatos = {META_KEY: meta.model_dump_json().encode("utf-8")}
    return pa.Table.from_pydict(columnas, schema=SCHEMA.with_metadata(metadatos))


def write_events(path: Path, meta: SessionMeta, events: Iterable[Event]) -> int:
    """Escribe la sesión en `path` de forma atómica; devuelve la cantidad de eventos."""
    tabla = to_table(meta, events)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporal = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(tabla, temporal, compression="zstd")
    temporal.replace(path)
    return int(tabla.num_rows)


def read_meta(path: Path) -> SessionMeta:
    """Lee solo la cabecera de la sesión."""
    metadatos = pq.read_schema(path).metadata or {}
    if META_KEY not in metadatos:
        raise ValueError(f"{path}: no es un archivo canónico de apexpulse (falta la cabecera)")
    return SessionMeta.model_validate_json(metadatos[META_KEY])


def read_events(path: Path, kinds: Sequence[str] | None = None) -> list[Event]:
    """Lee y valida los eventos en el orden guardado, opcionalmente filtrados por `kind`."""
    tabla = pq.read_table(path)
    eventos: list[Event] = []
    for fila in tabla.to_pylist():
        if kinds is not None and fila["kind"] not in kinds:
            continue
        datos = {k: v for k, v in fila.items() if v is not None and k != "seq"}
        eventos.append(EVENT_ADAPTER.validate_python(datos, strict=False))
    return eventos
