"""Adaptadores de fuente: lo único del código que conoce el formato de cada fuente (ADR 0002)."""

from apexpulse.sources.base import FetchReport, SchemaError, SourceAdapter, SourceError
from apexpulse.sources.openf1 import OpenF1Adapter

__all__ = ["FetchReport", "OpenF1Adapter", "SchemaError", "SourceAdapter", "SourceError"]
