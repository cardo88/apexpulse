"""Fixtures compartidos: red bloqueada, reloj falso y OpenF1 simulado con respuestas grabadas.

El reloj falso es `apexpulse.replay.clock.FakeClock`, el mismo que usan los tests del replay.
"""

from __future__ import annotations

import json
import socket
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from apexpulse.replay.clock import FakeClock as FakeClock  # re-export para los tests
from apexpulse.session_id import SessionId
from apexpulse.sources import Normalized, OpenF1Adapter
from apexpulse.sources.openf1 import RATE_LIMITS
from apexpulse.sources.ratelimit import RateLimiter

RAIZ = Path(__file__).resolve().parents[3]
FIXTURES = RAIZ / "fixtures" / "sessions"
# Ventana con las paradas de la primera tanda de São Paulo (vueltas 12 a 20), para el replay.
OPENF1_SAO_PAULO = FIXTURES / "2026-sao-paulo-r" / "openf1"
# Pocos registros por endpoint, solo para los tests de contrato del adaptador.
OPENF1_SAO_PAULO_CONTRATO = RAIZ / "fixtures" / "contract" / "2026-sao-paulo-r" / "openf1"
OPENF1_MONACO = FIXTURES / "2026-monaco-r" / "openf1"
# VSC en la vuelta 12, 18 y 34 de la carrera de Australia.
OPENF1_AUSTRALIA = FIXTURES / "2026-australia-r" / "openf1"
# Carrera completa de São Paulo solo con pit, stints, laps y race_control (sin intervalos).
OPENF1_SAO_PAULO_PARADAS = RAIZ / "fixtures" / "contract" / "2026-sao-paulo-r-paradas" / "openf1"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--golden-update",
        action="store_true",
        default=False,
        help="reescribe tests/golden/ con la salida actual (usar por make golden-update)",
    )


@pytest.fixture(autouse=True)
def sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ningún test abre conexiones: cualquier intento falla en el acto."""

    def bloqueado(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("los tests no usan la red: usar respuestas grabadas")

    monkeypatch.setattr(socket.socket, "connect", bloqueado)
    monkeypatch.setattr(socket, "create_connection", bloqueado)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


Responder = Callable[[httpx.Request], httpx.Response | None]


@dataclass
class FakeOpenF1:
    """Sirve los JSON de un directorio de fixtures como si fuera https://api.openf1.org/v1."""

    directorio: Path
    clock: FakeClock
    requests: list[httpx.Request] = field(default_factory=list)
    times: list[float] = field(default_factory=list)
    overrides: dict[str, list[httpx.Response]] = field(default_factory=dict)
    edits: dict[str, Callable[[list[dict[str, Any]]], list[dict[str, Any]]]] = field(
        default_factory=dict
    )

    def endpoint_json(self, endpoint: str) -> list[dict[str, Any]]:
        datos: list[dict[str, Any]] = json.loads(
            (self.directorio / f"{endpoint}.json").read_text(encoding="utf-8")
        )
        return datos

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.times.append(self.clock())
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if self.overrides.get(endpoint):
            return self.overrides[endpoint].pop(0)
        archivo = self.directorio / f"{endpoint}.json"
        if not archivo.exists():
            return httpx.Response(404, json={"detail": "Not Found"})
        datos = self.endpoint_json(endpoint)
        if endpoint in self.edits:
            datos = self.edits[endpoint](datos)
        return httpx.Response(200, json=datos)

    def client(self) -> httpx.Client:
        return httpx.Client(
            base_url="https://api.openf1.org/v1", transport=httpx.MockTransport(self.handler)
        )

    def paths(self) -> list[str]:
        return [r.url.path.rsplit("/", 1)[-1] for r in self.requests]


@pytest.fixture
def openf1(clock: FakeClock) -> Iterator[FakeOpenF1]:
    yield FakeOpenF1(OPENF1_SAO_PAULO_CONTRATO, clock)


@pytest.fixture
def openf1_monaco(clock: FakeClock) -> Iterator[FakeOpenF1]:
    """Tramo del SC y la bandera roja de 2026-monaco-r (session_key 11299)."""
    yield FakeOpenF1(OPENF1_MONACO, clock)


AHORA = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)


def normalizar_fixture(directorio: Path, session: str, raw: Path) -> Normalized:
    """Baja el fixture con el adaptador (OpenF1 simulado) y lo normaliza, como en producción."""
    reloj = FakeClock()
    fake = FakeOpenF1(directorio, reloj)
    limiter = RateLimiter(RATE_LIMITS, clock=reloj, sleep=reloj.sleep)
    adapter = OpenF1Adapter(fake.client(), limiter, sleep=reloj.sleep, now=lambda: AHORA)
    sid = SessionId.parse(session)
    adapter.fetch(sid, raw)
    return adapter.normalize(sid, raw)
