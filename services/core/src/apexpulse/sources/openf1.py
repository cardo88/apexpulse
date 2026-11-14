"""Adaptador de OpenF1: descarga histórica con caché local, límite de tasa y reintentos.

Flujo de `fetch` para `2026-sao-paulo-r`:
1. Si existe `data/raw/2026/2026-sao-paulo-r/openf1/manifest.json`, no hace requests.
2. Resuelve el session_key con `sessions?year=2026` (cacheado en `data/raw/2026/_openf1/`).
3. Pide cada endpoint con `?session_key=<n>`, valida el esquema y guarda el crudo en JSONL zstd.
4. Escribe el manifiesto al final: su presencia marca la descarga como completa.

`normalize` convierte ese crudo en eventos canónicos v1 (ver sources/openf1_normalize.py).

Límites de OpenF1 sin autenticación: 3 req/s y 30 req/min. Ante 429, 5xx o error de red
reintenta con backoff exponencial (o lo que indique Retry-After).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from apexpulse import __version__
from apexpulse.session_id import SESSION_TYPES, SessionId
from apexpulse.sources.base import FetchReport, Normalized, SchemaError, SourceError
from apexpulse.sources.openf1_normalize import normalize_openf1
from apexpulse.sources.ratelimit import RateLimiter
from apexpulse.sources.rawstore import read_jsonl_zst, write_json, write_jsonl_zst

BASE_URL = "https://api.openf1.org/v1"
SOURCE = "openf1"

# Límites publicados para el histórico sin autenticación: (periodo en segundos, requests).
RATE_LIMITS: tuple[tuple[float, int], ...] = ((1.0, 3), (60.0, 30))

# OpenF1 publica el histórico de una sesión 30 minutos después de que termina.
HISTORICAL_DELAY = timedelta(minutes=30)

MAX_RETRIES = 5
BACKOFF_BASE = 1.0  # segundos; el intento n espera BACKOFF_BASE * 2**n
BACKOFF_MAX = 60.0


@dataclass(frozen=True)
class EndpointSchema:
    """Campos obligatorios (su falta hace fallar la descarga) y conocidos (el resto avisa)."""

    required: frozenset[str]
    known: frozenset[str]


def _schema(required: str, extra: str = "") -> EndpointSchema:
    obligatorios = frozenset(required.split())
    return EndpointSchema(obligatorios, obligatorios | frozenset(extra.split()))


# Verificado contra la carrera 2026-sao-paulo-r (session_key 11412) el 2026-11-14.
SCHEMAS: dict[str, EndpointSchema] = {
    "sessions": _schema(
        "session_key meeting_key year session_name circuit_short_name date_start date_end",
        "session_type circuit_key country_key country_code country_name location gmt_offset "
        "is_cancelled",
    ),
    "laps": _schema(
        "session_key driver_number lap_number date_start lap_duration",
        "meeting_key duration_sector_1 duration_sector_2 duration_sector_3 i1_speed i2_speed "
        "st_speed is_pit_out_lap segments_sector_1 segments_sector_2 segments_sector_3",
    ),
    "stints": _schema(
        "session_key driver_number stint_number lap_start lap_end compound",
        "meeting_key tyre_age_at_start",
    ),
    "pit": _schema(
        "session_key driver_number lap_number date",
        "meeting_key pit_duration stop_duration lane_duration",
    ),
    "intervals": _schema(
        "session_key driver_number date gap_to_leader interval",
        "meeting_key",
    ),
    "position": _schema("session_key driver_number date position", "meeting_key"),
    "race_control": _schema(
        "session_key date category message",
        "meeting_key driver_number lap_number flag scope sector qualifying_phase",
    ),
    "weather": _schema(
        "session_key date air_temperature track_temperature rainfall",
        "meeting_key humidity pressure wind_direction wind_speed",
    ),
}

# Endpoints por sesión que usa el MVP, en el orden en que se descargan.
ENDPOINTS: tuple[str, ...] = (
    "laps",
    "stints",
    "pit",
    "intervals",
    "position",
    "race_control",
    "weather",
)

MANIFEST = "manifest.json"


def _default_client() -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        timeout=httpx.Timeout(60.0, connect=10.0),
        headers={"User-Agent": f"apexpulse/{__version__}"},
        follow_redirects=True,
    )


class OpenF1Adapter:
    """Descarga el histórico de una sesión desde OpenF1 al layout de data/raw."""

    name = SOURCE

    def __init__(
        self,
        client: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self._client = client or _default_client()
        self._limiter = limiter or RateLimiter(RATE_LIMITS, sleep=sleep)
        self._sleep = sleep
        self._now = now
        self._max_retries = max_retries

    # Rutas -----------------------------------------------------------------------------

    @staticmethod
    def session_dir(raw_root: Path, session: SessionId) -> Path:
        return raw_root / str(session.year) / str(session) / SOURCE

    @staticmethod
    def sessions_cache(raw_root: Path, year: int) -> Path:
        return raw_root / str(year) / f"_{SOURCE}" / "sessions.jsonl.zst"

    # Contrato ----------------------------------------------------------------------------

    def fetch(self, session: SessionId, dest: Path, *, force: bool = False) -> FetchReport:
        """Descarga los endpoints de `session` bajo `dest` (la raíz data/raw)."""
        destino = self.session_dir(dest, session)
        report = FetchReport(source=SOURCE, session=session, dest=destino)
        manifiesto = destino / MANIFEST

        if manifiesto.exists() and not force and self._cache_complete(destino, report):
            return report
        manifiesto.unlink(missing_ok=True)

        info = self._resolve(session, dest, report, force=force)
        session_key = int(info["session_key"])
        report.source_session_key = session_key

        archivos: dict[str, dict[str, Any]] = {}
        for endpoint in ENDPOINTS:
            registros = self._get(endpoint, {"session_key": session_key}, report)
            self._check_schema(endpoint, registros, report, session_key=session_key)
            if not registros:
                report.warnings.append(f"{endpoint}: OpenF1 no devolvió registros")
            archivo = f"{endpoint}.jsonl.zst"
            report.rows[endpoint] = write_jsonl_zst(destino / archivo, registros)
            archivos[endpoint] = {"file": archivo, "rows": report.rows[endpoint]}

        write_json(
            manifiesto,
            {
                "source": SOURCE,
                "session": str(session),
                "base_url": BASE_URL,
                "fetched_at": self._now().isoformat(timespec="seconds"),
                "openf1_session": info,
                "endpoints": archivos,
                "warnings": report.warnings,
            },
        )
        return report

    def normalize(self, session: SessionId, raw_root: Path) -> Normalized:
        """Convierte el crudo de `session` bajo `raw_root` (data/raw) en eventos canónicos v1."""
        try:
            return normalize_openf1(session, self.session_dir(raw_root, session))
        except ValidationError as error:
            raise SchemaError(
                f"OpenF1 {session}: un registro no cumple el modelo v1: {error}"
            ) from error

    # Caché -------------------------------------------------------------------------------

    def _cache_complete(self, destino: Path, report: FetchReport) -> bool:
        try:
            datos = json.loads((destino / MANIFEST).read_text(encoding="utf-8"))
            endpoints = datos["endpoints"]
            if any(e not in endpoints for e in ENDPOINTS):
                return False
            if any(not (destino / endpoints[e]["file"]).exists() for e in ENDPOINTS):
                return False
            report.rows = {e: int(endpoints[e]["rows"]) for e in ENDPOINTS}
            report.source_session_key = int(datos["openf1_session"]["session_key"])
            report.warnings = [str(w) for w in datos.get("warnings", [])]
        except (OSError, ValueError, KeyError, TypeError):
            return False
        report.from_cache = True
        return True

    # Resolución de la sesión -----------------------------------------------------------------

    def _resolve(
        self, session: SessionId, raw_root: Path, report: FetchReport, *, force: bool
    ) -> dict[str, Any]:
        cache = self.sessions_cache(raw_root, session.year)
        sesiones: list[dict[str, Any]] | None = None
        if cache.exists() and not force:
            sesiones = list(read_jsonl_zst(cache))
            elegida = self._match(session, sesiones)
            if elegida is not None:
                return self._check_available(session, elegida)
        # Sin caché o sin la sesión en caché (el calendario del año en curso se completa).
        sesiones = self._get("sessions", {"year": session.year}, report)
        self._check_schema("sessions", sesiones, report)
        write_jsonl_zst(cache, sesiones)
        elegida = self._match(session, sesiones)
        if elegida is None:
            circuitos = sorted({str(s.get("circuit_short_name")) for s in sesiones})
            raise SourceError(
                f"{session}: OpenF1 no tiene una sesión "
                f"{' o '.join(SESSION_TYPES[session.kind])} en "
                f"'{session.circuit_info.openf1}' para {session.year}. "
                f"Circuitos de OpenF1 en {session.year}: {', '.join(circuitos) or 'ninguno'}."
            )
        return self._check_available(session, elegida)

    @staticmethod
    def _match(session: SessionId, sesiones: list[dict[str, Any]]) -> dict[str, Any] | None:
        nombres = SESSION_TYPES[session.kind]
        candidatas = [
            s
            for s in sesiones
            if s.get("year") == session.year
            and s.get("circuit_short_name") == session.circuit_info.openf1
            and s.get("session_name") in nombres
        ]
        if len(candidatas) > 1:
            claves = ", ".join(str(s.get("session_key")) for s in candidatas)
            raise SourceError(f"{session}: más de una sesión coincide en OpenF1 ({claves}).")
        return candidatas[0] if candidatas else None

    def _check_available(self, session: SessionId, info: dict[str, Any]) -> dict[str, Any]:
        if info.get("is_cancelled"):
            raise SourceError(f"{session}: la sesión figura como cancelada en OpenF1.")
        try:
            fin = datetime.fromisoformat(str(info["date_end"]))
        except ValueError as error:
            raise SchemaError(f"{session}: date_end inválido: {info['date_end']!r}") from error
        disponible = fin + HISTORICAL_DELAY
        if self._now() < disponible:
            raise SourceError(
                f"{session}: la sesión termina {fin.isoformat()} y el histórico de OpenF1 "
                f"queda disponible desde {disponible.isoformat()}. Reintentar después."
            )
        return info

    # HTTP ----------------------------------------------------------------------------------

    def _get(
        self, endpoint: str, params: dict[str, Any], report: FetchReport
    ) -> list[dict[str, Any]]:
        ultimo = ""
        for intento in range(self._max_retries + 1):
            self._limiter.acquire()
            report.requests += 1
            try:
                respuesta = self._client.get(f"/{endpoint}", params=params)
            except httpx.TransportError as error:
                ultimo = f"error de red: {error}"
                espera = self._backoff(intento, None)
            else:
                if respuesta.status_code == 200:
                    return self._parse(endpoint, respuesta)
                if respuesta.status_code == 404 and "No results found" in respuesta.text:
                    return []
                if respuesta.status_code != 429 and respuesta.status_code < 500:
                    raise SourceError(
                        f"OpenF1 {endpoint} respondió {respuesta.status_code}: "
                        f"{respuesta.text[:200]}"
                    )
                ultimo = f"HTTP {respuesta.status_code}"
                espera = self._backoff(intento, respuesta.headers.get("Retry-After"))
            if intento < self._max_retries:
                self._sleep(espera)
        raise SourceError(
            f"OpenF1 {endpoint}: {ultimo} tras {self._max_retries + 1} intentos. "
            "Reintentar más tarde."
        )

    @staticmethod
    def _backoff(intento: int, retry_after: str | None) -> float:
        if retry_after is not None:
            try:
                return min(max(float(retry_after), 0.0), BACKOFF_MAX)
            except ValueError:
                pass  # Retry-After con fecha HTTP: se usa el backoff exponencial
        return min(BACKOFF_BASE * 2.0**intento, BACKOFF_MAX)

    @staticmethod
    def _parse(endpoint: str, respuesta: httpx.Response) -> list[dict[str, Any]]:
        try:
            datos = respuesta.json()
        except ValueError as error:
            raise SchemaError(f"OpenF1 {endpoint}: la respuesta no es JSON") from error
        if not isinstance(datos, list) or not all(isinstance(r, dict) for r in datos):
            raise SchemaError(f"OpenF1 {endpoint}: se esperaba una lista de objetos JSON")
        return datos

    # Esquema -------------------------------------------------------------------------------

    @staticmethod
    def _check_schema(
        endpoint: str,
        registros: list[dict[str, Any]],
        report: FetchReport,
        *,
        session_key: int | None = None,
    ) -> None:
        esquema = SCHEMAS[endpoint]
        desconocidos: dict[str, Any] = {}
        for indice, registro in enumerate(registros):
            faltantes = esquema.required - registro.keys()
            if faltantes:
                raise SchemaError(
                    f"OpenF1 {endpoint}: el registro {indice} no tiene "
                    f"{', '.join(sorted(faltantes))}. Muestra: {str(registro)[:300]}"
                )
            if session_key is not None and registro["session_key"] != session_key:
                raise SchemaError(
                    f"OpenF1 {endpoint}: el registro {indice} es de la sesión "
                    f"{registro['session_key']}, no de {session_key}"
                )
            for campo in registro.keys() - esquema.known:
                desconocidos.setdefault(campo, registro[campo])
        if desconocidos:
            muestra = ", ".join(f"{k}={v!r}" for k, v in sorted(desconocidos.items()))
            report.warnings.append(f"{endpoint}: campos desconocidos: {muestra[:300]}")
