"""Modelo canónico de eventos v1 y su persistencia en Parquet (ADR 0002 y 0005)."""

from apexpulse.model.events import (
    EVENT_ADAPTER,
    NEUTRALIZED,
    SCHEMA_VERSION,
    Compound,
    Event,
    IntervalUpdated,
    LapCompleted,
    PitLane,
    PositionChanged,
    RaceControlMessage,
    SessionMeta,
    StintStarted,
    TrackStatus,
    TrackStatusChanged,
    WeatherSample,
    sort_key,
)
from apexpulse.model.parquet import read_events, read_meta, write_events

__all__ = [
    "EVENT_ADAPTER",
    "NEUTRALIZED",
    "SCHEMA_VERSION",
    "Compound",
    "Event",
    "IntervalUpdated",
    "LapCompleted",
    "PitLane",
    "PositionChanged",
    "RaceControlMessage",
    "SessionMeta",
    "StintStarted",
    "TrackStatus",
    "TrackStatusChanged",
    "WeatherSample",
    "read_events",
    "read_meta",
    "sort_key",
    "write_events",
]
