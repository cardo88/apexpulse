"""Escaneo de solo lectura de las carreras de un año en OpenF1, para elegir sesiones.

`make escanear YEAR=2026` pide `sessions`, `weather`, `race_control` y `pit` (no `laps`,
`stints`, `intervals`, `position` ni `drivers`: liviano a propósito, para decidir qué sesiones
bajar con `make fetch`, no para normalizarlas). Respeta el mismo límite de tasa que `fetch`
(`RATE_LIMITS`) y cachea el crudo pedido bajo `data/raw/<año>/_escaneo/<session_key>/`, separado
de la caché de `fetch` (que exige los ocho endpoints para considerar una sesión completa).

El estado de pista se deriva con `sources.trackstatus.derive_track_status`, la misma función que
usa el normalizador: un filtro propio que buscara la subcadena `"RED FLAG"` en el mensaje
confundiría `"CHEQUERED FLAG"` con una bandera roja real (contiene "...chequ-ERED FLAG"); ver
docs/fuentes-de-datos.md. Sin datos de `laps`, un `*_ENDING` no se cierra solo al empezar la
vuelta siguiente (`derive_track_status` necesita `leader_lap_starts`, que este escaneo no pide):
queda neutralizado hasta el próximo mensaje de dirección de carrera. Subestima levemente las
paradas en verde cerca del final de un `*_ENDING`; aceptable para elegir candidatas, no para
calibrar.

"Parada con detención" es `pit.stop_duration is not None`, no la definición de parada real de
`cheap_stop` (que también cuenta cambios de neumáticos sin detención, vía stints): esta función
es para elegir candidatas rápido, no para contar paradas con precisión. La tarea de calibración
usa la definición de `cheap_stop` sobre las sesiones ya bajadas.

Ante 429 o 5xx reintenta con el mismo backoff exponencial que `fetch` (verificado en la
práctica: OpenF1 devolvió 429 a la cuarta request de una corrida real de este escaneo, muy por
debajo de 3 req/s y 30 req/min, así que el límite real es más estricto que el publicado o se
comparte con otro uso reciente de la misma IP).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from apexpulse.model.events import RaceControlMessage, TrackStatus
from apexpulse.session_id import circuits
from apexpulse.sources.base import SourceError
from apexpulse.sources.openf1 import (
    BACKOFF_BASE,
    BACKOFF_MAX,
    HISTORICAL_DELAY,
    MAX_RETRIES,
    RATE_LIMITS,
    default_client,
)
from apexpulse.sources.ratelimit import RateLimiter
from apexpulse.sources.rawstore import read_jsonl_zst, write_jsonl_zst
from apexpulse.sources.trackstatus import derive_track_status


@dataclass(frozen=True)
class Escaneo:
    """Métricas de una sesión de carrera, para decidir si sirve como fixture o calibración."""

    session_key: int
    circuito: str  # circuit_short_name de OpenF1
    slug: str | None  # None si el circuito no está en circuits.toml
    fecha: str  # date_start, solo la fecha
    ya_usada: bool  # existe fixtures/sessions/<slug>-r
    disponible: bool  # no cancelada y pasaron 30 min de date_end
    lluvia: bool | None = None
    paradas_con_detencion: int | None = None
    paradas_en_verde: int | None = None
    periodos_sc_vsc: int | None = None
    bandera_roja: bool | None = None
    avisos: tuple[str, ...] = ()


def _slug_por_circuito() -> dict[str, str]:
    return {c.openf1: slug for slug, c in circuits().items()}


def _instante(valor: str) -> datetime:
    return datetime.fromisoformat(valor)


def _race_control_rows(filas: list[dict[str, Any]]) -> list[RaceControlMessage]:
    return [
        RaceControlMessage(
            t=_instante(fila["date"]),
            category=str(fila["category"]),
            message=str(fila["message"]),
            flag=None if fila.get("flag") is None else str(fila["flag"]),
            scope=None if fila.get("scope") is None else str(fila["scope"]),
            sector=None if fila.get("sector") is None else int(fila["sector"]),
            driver=None if fila.get("driver_number") is None else int(fila["driver_number"]),
            lap=None if fila.get("lap_number") is None else int(fila["lap_number"]),
        )
        for fila in filas
    ]


def _estado_en(periodos: list[tuple[datetime, TrackStatus]], t: datetime) -> TrackStatus:
    """Último estado derivado con inicio <= t; `GREEN` si es anterior al primero."""
    vigente = TrackStatus.GREEN
    for inicio, estado in periodos:
        if inicio > t:
            break
        vigente = estado
    return vigente


class _Cache:
    """Crudo pedido por `escanear`, bajo `data/raw/<año>/_escaneo/<session_key>/`."""

    def __init__(self, raw_root: Path, year: int) -> None:
        self._raiz = raw_root / str(year) / "_escaneo"

    def leer_o_pedir(
        self,
        session_key: int,
        endpoint: str,
        get: Callable[[str, dict[str, Any]], list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        archivo = self._raiz / str(session_key) / f"{endpoint}.jsonl.zst"
        if archivo.exists():
            return list(read_jsonl_zst(archivo))
        filas = get(endpoint, {"session_key": session_key})
        write_jsonl_zst(archivo, filas)
        return filas


def escanear_anio(
    year: int,
    *,
    raw_root: Path,
    fixtures_root: Path,
    excluir: frozenset[str] = frozenset(),
    client: httpx.Client | None = None,
    limiter: RateLimiter | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[Escaneo]:
    """Escanea las sesiones de carrera (`session_name=Race`) de `year`, sin normalizarlas.

    `excluir` son slugs de `circuits.toml` a saltear (por ejemplo, los ya elegidos a mano).
    """
    cliente = client or default_client()
    limitador = limiter or RateLimiter(RATE_LIMITS, sleep=sleep)
    cache = _Cache(raw_root, year)
    slugs = _slug_por_circuito()

    def get(endpoint: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        ultimo = ""
        for intento in range(MAX_RETRIES + 1):
            limitador.acquire()
            try:
                respuesta = cliente.get(f"/{endpoint}", params=params)
            except httpx.TransportError as error:
                ultimo = f"error de red: {error}"
                espera = min(BACKOFF_BASE * 2.0**intento, BACKOFF_MAX)
            else:
                if respuesta.status_code == 200:
                    datos = respuesta.json()
                    return datos if isinstance(datos, list) else []
                if respuesta.status_code != 429 and respuesta.status_code < 500:
                    raise SourceError(
                        f"OpenF1 {endpoint} respondió {respuesta.status_code}: "
                        f"{respuesta.text[:200]}"
                    )
                ultimo = f"HTTP {respuesta.status_code}"
                reintentar_tras = respuesta.headers.get("Retry-After")
                try:
                    espera = (
                        min(max(float(reintentar_tras), 0.0), BACKOFF_MAX)
                        if reintentar_tras is not None
                        else min(BACKOFF_BASE * 2.0**intento, BACKOFF_MAX)
                    )
                except ValueError:
                    espera = min(BACKOFF_BASE * 2.0**intento, BACKOFF_MAX)
            if intento < MAX_RETRIES:
                sleep(espera)
        raise SourceError(f"OpenF1 {endpoint}: {ultimo} tras {MAX_RETRIES + 1} intentos.")

    sesiones = get("sessions", {"year": year})
    resultados: list[Escaneo] = []
    for sesion in sorted(
        (s for s in sesiones if s.get("session_name") == "Race"), key=lambda s: s["date_start"]
    ):
        circuito = str(sesion["circuit_short_name"])
        slug = slugs.get(circuito)
        if slug is not None and slug in excluir:
            continue
        session_key = int(sesion["session_key"])
        ya_usada = slug is not None and (fixtures_root / f"{year}-{slug}-r").exists()
        fin = _instante(sesion["date_end"])
        disponible = not sesion.get("is_cancelled") and now() >= fin + HISTORICAL_DELAY
        base = Escaneo(
            session_key=session_key,
            circuito=circuito,
            slug=slug,
            fecha=str(sesion["date_start"])[:10],
            ya_usada=ya_usada,
            disponible=disponible,
        )
        if not disponible:
            resultados.append(base)
            continue

        avisos: tuple[str, ...] = (
            () if slug is not None else (f"circuito sin slug en circuits.toml: {circuito}",)
        )
        weather = cache.leer_o_pedir(session_key, "weather", get)
        rc = cache.leer_o_pedir(session_key, "race_control", get)
        pit = cache.leer_o_pedir(session_key, "pit", get)

        mensajes = _race_control_rows(rc)
        cambios = sorted(derive_track_status(mensajes, {}), key=lambda c: c.t)
        periodos = [(c.t, c.status) for c in cambios]
        con_detencion = [p for p in pit if p.get("stop_duration") is not None]
        en_verde = [
            p
            for p in con_detencion
            if _estado_en(periodos, _instante(p["date"])) == TrackStatus.GREEN
        ]

        resultados.append(
            Escaneo(
                session_key=session_key,
                circuito=circuito,
                slug=slug,
                fecha=base.fecha,
                ya_usada=ya_usada,
                disponible=True,
                lluvia=any(w.get("rainfall") for w in weather),
                paradas_con_detencion=len(con_detencion),
                paradas_en_verde=len(en_verde),
                periodos_sc_vsc=sum(
                    1 for c in cambios if c.status in (TrackStatus.SC, TrackStatus.VSC)
                ),
                bandera_roja=any(c.status == TrackStatus.RED for c in cambios),
                avisos=tuple(avisos),
            )
        )
    return resultados
