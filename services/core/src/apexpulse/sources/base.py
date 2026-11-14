"""Contrato común de los adaptadores de fuente: descarga del crudo y normalización a eventos v1."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from apexpulse.model.events import Event, SessionMeta
from apexpulse.session_id import SessionId


class SourceError(RuntimeError):
    """Error de una fuente que impide completar la descarga."""


class SchemaError(SourceError):
    """La respuesta de la fuente no cumple el esquema esperado (falta un campo obligatorio)."""


@dataclass
class FetchReport:
    """Resultado de `SourceAdapter.fetch`."""

    source: str
    session: SessionId
    dest: Path
    source_session_key: int | None = None
    rows: dict[str, int] = field(default_factory=dict)  # endpoint -> registros guardados
    requests: int = 0  # requests HTTP hechos, incluidos reintentos
    from_cache: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class Normalized:
    """Resultado de `SourceAdapter.normalize`: cabecera, eventos sin ordenar y avisos."""

    meta: SessionMeta
    events: list[Event]
    warnings: list[str] = field(default_factory=list)


class SourceAdapter(Protocol):
    """Adaptador aislado de una fuente. Ninguna otra parte del código conoce su formato."""

    name: str  # "openf1", "f1static", "jolpica", "f1live"

    def fetch(self, session: SessionId, dest: Path, *, force: bool = False) -> FetchReport:
        """Descarga el crudo de la sesión a `dest` (data/raw), o lo reutiliza si ya está."""
        ...

    def normalize(self, session: SessionId, raw_root: Path) -> Normalized:
        """Convierte el crudo ya descargado bajo `raw_root` (data/raw) en eventos canónicos v1."""
        ...
