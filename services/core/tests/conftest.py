"""Fixtures compartidos: red bloqueada, reloj falso y OpenF1 simulado con respuestas grabadas."""

from __future__ import annotations

import json
import socket
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

RAIZ = Path(__file__).resolve().parents[3]
FIXTURES = RAIZ / "fixtures" / "sessions"
OPENF1_SAO_PAULO = FIXTURES / "2026-sao-paulo-r" / "openf1"
OPENF1_MONACO = FIXTURES / "2026-monaco-r" / "openf1"


@pytest.fixture(autouse=True)
def sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ningún test abre conexiones: cualquier intento falla en el acto."""

    def bloqueado(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("los tests no usan la red: usar respuestas grabadas")

    monkeypatch.setattr(socket.socket, "connect", bloqueado)
    monkeypatch.setattr(socket, "create_connection", bloqueado)


@dataclass
class FakeClock:
    """Reloj controlado: `sleep` avanza el tiempo sin esperar."""

    t: float = 1_000_000.0
    sleeps: list[float] = field(default_factory=list)

    def __call__(self) -> float:
        return self.t

    def sleep(self, segundos: float) -> None:
        self.sleeps.append(segundos)
        self.t += segundos


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
    yield FakeOpenF1(OPENF1_SAO_PAULO, clock)


@pytest.fixture
def openf1_monaco(clock: FakeClock) -> Iterator[FakeOpenF1]:
    """Tramo del SC y la bandera roja de 2026-monaco-r (session_key 11299)."""
    yield FakeOpenF1(OPENF1_MONACO, clock)
