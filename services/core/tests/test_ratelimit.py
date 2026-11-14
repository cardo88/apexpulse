"""Tests del límite de tasa por ventanas deslizantes."""

from __future__ import annotations

from pathlib import Path

import pytest

from apexpulse.sources.openf1 import RATE_LIMITS
from apexpulse.sources.ratelimit import RateLimiter
from conftest import FakeClock


def _max_en_ventana(tiempos: list[float], periodo: float) -> int:
    return max(sum(1 for u in tiempos if t <= u < t + periodo) for t in tiempos)


def test_respeta_3_por_segundo_y_30_por_minuto(clock: FakeClock) -> None:
    limiter = RateLimiter(RATE_LIMITS, clock=clock, sleep=clock.sleep)
    tiempos = []
    for _ in range(95):
        limiter.acquire()
        tiempos.append(clock())
    assert _max_en_ventana(tiempos, 1.0) == 3
    assert _max_en_ventana(tiempos, 60.0) == 30
    # 95 requests: tres minutos completos de 30 más 5; el último sale después de 180 s.
    assert tiempos[-1] - tiempos[0] >= 180.0


def test_los_primeros_3_no_esperan(clock: FakeClock) -> None:
    limiter = RateLimiter(RATE_LIMITS, clock=clock, sleep=clock.sleep)
    for _ in range(3):
        limiter.acquire()
    assert clock.sleeps == []
    assert limiter.wait_time() == pytest.approx(1.0)


def test_estado_compartido_entre_ejecuciones(tmp_path: Path, clock: FakeClock) -> None:
    estado = tmp_path / "state" / "openf1-ratelimit.json"
    primero = RateLimiter(RATE_LIMITS, clock=clock, sleep=clock.sleep, state_file=estado)
    for _ in range(30):
        primero.acquire()
    clock.t += 5.0
    segundo = RateLimiter(RATE_LIMITS, clock=clock, sleep=clock.sleep, state_file=estado)
    assert segundo.wait_time() > 40.0  # el minuto todavía tiene 30 requests


def test_estado_viejo_o_corrupto_se_ignora(tmp_path: Path, clock: FakeClock) -> None:
    estado = tmp_path / "openf1-ratelimit.json"
    estado.write_text("[1.0, 2.0, 3.0]", encoding="utf-8")  # hace más de un minuto
    assert RateLimiter(RATE_LIMITS, clock=clock, state_file=estado).wait_time() == 0.0
    estado.write_text("{no es json", encoding="utf-8")
    assert RateLimiter(RATE_LIMITS, clock=clock, state_file=estado).wait_time() == 0.0


def test_ventana_invalida() -> None:
    with pytest.raises(ValueError):
        RateLimiter([(0.0, 3)])
