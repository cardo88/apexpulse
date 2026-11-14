"""Normalizador de OpenF1: del crudo en data/raw a eventos canónicos v1.

Lee los `<endpoint>.jsonl.zst` que dejó `OpenF1Adapter.fetch` y los convierte campo por campo
según la tabla de mapeo de docs/fuentes-de-datos.md. El estado de pista no existe en OpenF1:
se deriva de `race_control` con `trackstatus.derive_track_status`.

Los registros que no se pueden ubicar en el tiempo se omiten y se informan como aviso, agrupados
por motivo, por ejemplo `laps: 2 vueltas sin tiempo ni vuelta siguiente, omitidas`.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from apexpulse.model.events import (
    Compound,
    Event,
    IntervalUpdated,
    LapCompleted,
    PitLane,
    PositionChanged,
    RaceControlMessage,
    SessionMeta,
    StintStarted,
    WeatherSample,
)
from apexpulse.session_id import SessionId
from apexpulse.sources.base import Normalized, SchemaError, SourceError
from apexpulse.sources.rawstore import read_jsonl_zst
from apexpulse.sources.trackstatus import derive_track_status

SOURCE = "openf1"
MANIFEST = "manifest.json"

_RE_VUELTAS = re.compile(r"^\+(\d+) LAPS?$")


def _instante(valor: Any, contexto: str) -> datetime:
    try:
        return datetime.fromisoformat(str(valor))
    except ValueError as error:
        raise SchemaError(f"OpenF1 {contexto}: fecha inválida {valor!r}") from error


def _f(valor: Any) -> float | None:
    return None if valor is None else float(valor)


def _i(valor: Any) -> int | None:
    return None if valor is None else round(float(valor))


def _vueltas_o_segundos(valor: Any) -> tuple[float | None, int | None]:
    """`1.234` -> (1.234, None); `"+1 LAP"` -> (None, 1); `None` -> (None, None)."""
    if valor is None or isinstance(valor, bool):
        return None, None
    if isinstance(valor, int | float):
        return float(valor), None
    coincidencia = _RE_VUELTAS.match(str(valor).strip())
    if coincidencia is None:
        raise ValueError(str(valor))
    return None, int(coincidencia.group(1))


@dataclass
class _Avisos:
    conteo: Counter[str] = field(default_factory=Counter)
    muestras: dict[str, str] = field(default_factory=dict)

    def sumar(self, motivo: str, muestra: str = "") -> None:
        self.conteo[motivo] += 1
        self.muestras.setdefault(motivo, muestra)

    def lista(self) -> list[str]:
        salida = []
        for motivo, n in sorted(self.conteo.items()):
            muestra = self.muestras[motivo]
            salida.append(f"{motivo}: {n}" + (f" (por ejemplo {muestra})" if muestra else ""))
        return salida


def normalize_openf1(session: SessionId, destino: Path) -> Normalized:
    """Normaliza el crudo de `destino` (data/raw/<año>/<sesion>/openf1)."""
    manifiesto = destino / MANIFEST
    if not manifiesto.exists():
        raise SourceError(
            f"{session}: no hay crudo completo de OpenF1 en {destino}. "
            f"Correr primero: make fetch SESSION={session}"
        )
    datos = json.loads(manifiesto.read_text(encoding="utf-8"))
    info = datos["openf1_session"]

    def leer(endpoint: str) -> list[dict[str, Any]]:
        return list(read_jsonl_zst(destino / datos["endpoints"][endpoint]["file"]))

    avisos = _Avisos()
    eventos: list[Event] = []

    vueltas, inicio_de_vuelta = _laps(leer("laps"), avisos)
    eventos += vueltas
    eventos += _stints(leer("stints"), inicio_de_vuelta, avisos)
    eventos += _pits(leer("pit"))
    eventos += _positions(leer("position"))
    eventos += _intervals(leer("intervals"), avisos)
    mensajes = _race_control(leer("race_control"))
    eventos += mensajes
    eventos += _weather(leer("weather"))

    inicio_del_lider: dict[int, datetime] = {}
    for (_piloto, vuelta), t in inicio_de_vuelta.items():
        if vuelta not in inicio_del_lider or t < inicio_del_lider[vuelta]:
            inicio_del_lider[vuelta] = t
    eventos += derive_track_status(mensajes, inicio_del_lider)

    meta = SessionMeta(
        session=str(session),
        source=SOURCE,
        source_session_key=int(info["session_key"]),
        circuit=session.circuit_info.nombre,
        start=_instante(info["date_start"], "sessions"),
        end=_instante(info["date_end"], "sessions"),
    )
    return Normalized(meta=meta, events=eventos, warnings=avisos.lista())


def _laps(
    filas: list[dict[str, Any]], avisos: _Avisos
) -> tuple[list[Event], dict[tuple[int, int], datetime]]:
    inicio: dict[tuple[int, int], datetime] = {}
    por_piloto: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for fila in filas:
        if fila["date_start"] is None:
            avisos.sumar(
                "laps: vueltas sin date_start, omitidas",
                f"piloto {fila['driver_number']} vuelta {fila['lap_number']}",
            )
            continue
        piloto, vuelta = int(fila["driver_number"]), int(fila["lap_number"])
        inicio[(piloto, vuelta)] = _instante(fila["date_start"], "laps")
        por_piloto[piloto].append(fila)

    eventos: list[Event] = []
    for piloto, propias in por_piloto.items():
        for fila in propias:
            vuelta = int(fila["lap_number"])
            duracion = fila["lap_duration"]
            if duracion is not None:
                fin = inicio[(piloto, vuelta)] + timedelta(seconds=float(duracion))
            elif (piloto, vuelta + 1) in inicio:
                fin = inicio[(piloto, vuelta + 1)]
            else:
                avisos.sumar(
                    "laps: vueltas sin tiempo ni vuelta siguiente, omitidas",
                    f"piloto {piloto} vuelta {vuelta}",
                )
                continue
            eventos.append(
                LapCompleted(
                    t=fin,
                    driver=piloto,
                    lap=vuelta,
                    lap_time_s=None if duracion is None else float(duracion),
                    s1_s=_f(fila.get("duration_sector_1")),
                    s2_s=_f(fila.get("duration_sector_2")),
                    s3_s=_f(fila.get("duration_sector_3")),
                    pit_out=bool(fila.get("is_pit_out_lap")),
                )
            )
    return eventos, inicio


def _stints(
    filas: list[dict[str, Any]], inicio: dict[tuple[int, int], datetime], avisos: _Avisos
) -> list[Event]:
    eventos: list[Event] = []
    for fila in filas:
        piloto, vuelta = int(fila["driver_number"]), int(fila["lap_start"])
        muestra = f"piloto {piloto} stint {fila['stint_number']}"
        t = inicio.get((piloto, vuelta))
        if t is None:
            avisos.sumar("stints: la vuelta de inicio no está en laps, omitidos", muestra)
            continue
        edad = fila.get("tyre_age_at_start")
        if edad is None:
            avisos.sumar("stints: sin tyre_age_at_start, omitidos", muestra)
            continue
        try:
            compuesto = Compound(str(fila["compound"]).upper())
        except ValueError:
            avisos.sumar("stints: compuesto desconocido, UNKNOWN", str(fila["compound"]))
            compuesto = Compound.UNKNOWN
        eventos.append(
            StintStarted(
                t=t,
                driver=piloto,
                lap=vuelta,
                stint=int(fila["stint_number"]),
                compound=compuesto,
                tyre_age=int(edad),
            )
        )
    return eventos


def _pits(filas: list[dict[str, Any]]) -> list[Event]:
    eventos: list[Event] = []
    for fila in filas:
        carril = _f(fila.get("lane_duration"))
        if carril is None:
            carril = _f(fila.get("pit_duration"))
        eventos.append(
            PitLane(
                t=_instante(fila["date"], "pit"),
                driver=int(fila["driver_number"]),
                lap=int(fila["lap_number"]),
                lane_s=carril,
                stationary_s=_f(fila.get("stop_duration")),
            )
        )
    return eventos


def _positions(filas: list[dict[str, Any]]) -> list[Event]:
    return [
        PositionChanged(
            t=_instante(fila["date"], "position"),
            driver=int(fila["driver_number"]),
            position=int(fila["position"]),
        )
        for fila in filas
    ]


def _intervals(filas: list[dict[str, Any]], avisos: _Avisos) -> list[Event]:
    eventos: list[Event] = []
    for fila in filas:
        try:
            gap, doblado = _vueltas_o_segundos(fila["gap_to_leader"])
            intervalo, intervalo_vueltas = _vueltas_o_segundos(fila["interval"])
        except ValueError as error:
            avisos.sumar("intervals: valor no reconocido, omitidos", str(error))
            continue
        if gap is None and doblado is None and intervalo is None and intervalo_vueltas is None:
            continue  # la fuente no tiene distancia para ese instante
        eventos.append(
            IntervalUpdated(
                t=_instante(fila["date"], "intervals"),
                driver=int(fila["driver_number"]),
                gap_s=gap,
                laps_down=doblado,
                interval_s=intervalo,
                interval_laps=intervalo_vueltas,
            )
        )
    return eventos


def _race_control(filas: list[dict[str, Any]]) -> list[RaceControlMessage]:
    return [
        RaceControlMessage(
            t=_instante(fila["date"], "race_control"),
            category=str(fila["category"]),
            message=str(fila["message"]),
            flag=None if fila.get("flag") is None else str(fila["flag"]),
            scope=None if fila.get("scope") is None else str(fila["scope"]),
            sector=_i(fila.get("sector")),
            driver=_i(fila.get("driver_number")),
            lap=_i(fila.get("lap_number")),
        )
        for fila in filas
    ]


def _weather(filas: list[dict[str, Any]]) -> list[Event]:
    return [
        WeatherSample(
            t=_instante(fila["date"], "weather"),
            air_c=float(fila["air_temperature"]),
            track_c=float(fila["track_temperature"]),
            rain=bool(fila["rainfall"]),
            humidity_pct=_f(fila.get("humidity")),
            wind_ms=_f(fila.get("wind_speed")),
            wind_deg=_i(fila.get("wind_direction")),
            pressure_hpa=_f(fila.get("pressure")),
        )
        for fila in filas
    ]
