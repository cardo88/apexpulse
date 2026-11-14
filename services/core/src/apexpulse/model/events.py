"""Eventos canónicos v1: el contrato entre los adaptadores de fuente y el resto del sistema.

Cada evento es inmutable, tiene un instante `t` en UTC y un `kind` que lo discrimina. Las
reglas, el replay y la API solo conocen estos tipos, nunca el formato de una fuente (ADR 0002).
Esquema, ejemplos y reglas de versionado en docs/modelo-de-eventos.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, TypeAdapter

# MAYOR.MENOR. MENOR suma campos opcionales o tipos nuevos; MAYOR rompe compatibilidad y obliga
# a renormalizar desde el crudo (ADR 0005).
SCHEMA_VERSION = "1.0"


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError("el instante debe tener zona horaria")
    return valor.astimezone(UTC)


Instante = Annotated[datetime, AfterValidator(_utc)]
Piloto = Annotated[int, Field(ge=1, le=99)]
Vuelta = Annotated[int, Field(ge=0, le=200)]
Segundos = Annotated[float, Field(ge=0)]
NoNegativo = Annotated[float, Field(ge=0)]


class Compound(StrEnum):
    """Compuesto de neumático."""

    SOFT = "SOFT"
    MEDIUM = "MEDIUM"
    HARD = "HARD"
    INTERMEDIATE = "INTERMEDIATE"
    WET = "WET"
    UNKNOWN = "UNKNOWN"


class TrackStatus(StrEnum):
    """Estado de pista para toda la sesión. Los `*_ENDING` siguen siendo neutralización."""

    GREEN = "GREEN"
    SC = "SC"
    SC_ENDING = "SC_ENDING"
    VSC = "VSC"
    VSC_ENDING = "VSC_ENDING"
    RED = "RED"
    FINISHED = "FINISHED"


NEUTRALIZED = frozenset(
    {TrackStatus.SC, TrackStatus.SC_ENDING, TrackStatus.VSC, TrackStatus.VSC_ENDING}
)


class _Evento(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    t: Instante


class LapCompleted(_Evento):
    """Un piloto completa una vuelta. `t` es el instante en que cruza la línea."""

    kind: Literal["lap"] = "lap"
    driver: Piloto
    lap: Vuelta
    lap_time_s: Segundos | None = None  # None: la fuente no tiene el tiempo (vuelta 1, rojo)
    s1_s: Segundos | None = None
    s2_s: Segundos | None = None
    s3_s: Segundos | None = None
    pit_out: bool = False  # la vuelta empieza en la salida de boxes


class StintStarted(_Evento):
    """Empieza un stint. `t` es el inicio de la vuelta `lap`; no anticipa cuándo termina."""

    kind: Literal["stint"] = "stint"
    driver: Piloto
    lap: Vuelta
    stint: Annotated[int, Field(ge=1)]
    compound: Compound
    tyre_age: Annotated[int, Field(ge=0)]  # vueltas que tenía el juego al empezar el stint


class PitLane(_Evento):
    """Paso por el pit lane. `stationary_s` None: no hay detención registrada."""

    kind: Literal["pit"] = "pit"
    driver: Piloto
    lap: Vuelta
    lane_s: Segundos | None = None  # tiempo entre la entrada y la salida del pit lane
    stationary_s: Segundos | None = None  # tiempo detenido en el box


class PositionChanged(_Evento):
    """Nueva posición de un piloto en la clasificación de la sesión."""

    kind: Literal["position"] = "position"
    driver: Piloto
    position: Annotated[int, Field(ge=1, le=99)]


class IntervalUpdated(_Evento):
    """Distancia al líder y al auto de adelante.

    Un auto doblado tiene `laps_down` y `gap_s` None. Si la fuente informa vueltas también en el
    intervalo, `interval_laps` las lleva y `interval_s` queda None.
    """

    kind: Literal["interval"] = "interval"
    driver: Piloto
    gap_s: Segundos | None = None
    laps_down: Annotated[int, Field(ge=1)] | None = None
    interval_s: Segundos | None = None
    interval_laps: Annotated[int, Field(ge=1)] | None = None


class RaceControlMessage(_Evento):
    """Mensaje de dirección de carrera, tal como lo publica la FIA (en inglés)."""

    kind: Literal["race_control"] = "race_control"
    category: str
    message: str
    flag: str | None = None
    scope: str | None = None
    sector: Annotated[int, Field(ge=0)] | None = None
    driver: Piloto | None = None
    lap: Vuelta | None = None  # vuelta del líder cuando se emitió


class TrackStatusChanged(_Evento):
    """Cambio de estado de pista, derivado de los mensajes de dirección de carrera."""

    kind: Literal["track_status"] = "track_status"
    status: TrackStatus
    lap: Vuelta | None = None  # vuelta del líder
    cause: str  # mensaje o regla que produjo el cambio


class WeatherSample(_Evento):
    """Muestra de la estación meteorológica del circuito."""

    kind: Literal["weather"] = "weather"
    air_c: float
    track_c: float
    rain: bool
    humidity_pct: Annotated[float, Field(ge=0, le=100)] | None = None
    wind_ms: NoNegativo | None = None
    wind_deg: Annotated[int, Field(ge=0, le=360)] | None = None
    pressure_hpa: NoNegativo | None = None


Event = Annotated[
    LapCompleted
    | StintStarted
    | PitLane
    | PositionChanged
    | IntervalUpdated
    | RaceControlMessage
    | TrackStatusChanged
    | WeatherSample,
    Field(discriminator="kind"),
]

EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)

# Orden de desempate para eventos con el mismo instante: primero lo que cambia el contexto.
KIND_ORDER: dict[str, int] = {
    "race_control": 0,
    "track_status": 1,
    "lap": 2,
    "pit": 3,
    "stint": 4,
    "position": 5,
    "interval": 6,
    "weather": 7,
}


def sort_key(evento: Event) -> tuple[datetime, int, int, int, str]:
    """Orden total y determinístico del flujo: instante, tipo, piloto, vuelta y contenido.

    El contenido desempata eventos simultáneos del mismo tipo, por ejemplo dos mensajes de
    dirección de carrera con el mismo instante, sin depender del orden de la fuente.
    """
    piloto = getattr(evento, "driver", None)
    vuelta = getattr(evento, "lap", None)
    return (
        evento.t,
        KIND_ORDER[evento.kind],
        -1 if piloto is None else piloto,
        -1 if vuelta is None else vuelta,
        evento.model_dump_json(),
    )


class SessionMeta(BaseModel):
    """Cabecera de una sesión normalizada; viaja en los metadatos del Parquet."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = SCHEMA_VERSION
    session: str  # identificador <año>-<circuito>-<tipo>
    source: str
    source_session_key: int | None = None
    circuit: str
    start: Instante
    end: Instante
