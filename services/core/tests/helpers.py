"""Ayudas de los tests de salida completa: pipeline desde fixtures, serialización y golden.

El pipeline es el de producción con la red simulada: fixtures grabados, el adaptador de OpenF1
sobre `httpx.MockTransport`, el normalizador, el Parquet canónico y el replay con el motor de
lecturas. Un golden es la salida esperada de una regla sobre una sesión, en JSON legible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from apexpulse.model import write_events
from apexpulse.readings import Engine, Reading
from apexpulse.replay import ConsolePrinter, FakeClock, Replay
from conftest import (
    OPENF1_AUSTRALIA,
    OPENF1_BARCELONA,
    OPENF1_HUNGRIA,
    OPENF1_MONACO,
    OPENF1_SAO_PAULO,
    normalizar_fixture,
)

GOLDEN = Path(__file__).resolve().parent / "golden"

# Las carreras con fixtures de sessions/: ventanas de la carrera, no carreras completas.
FIXTURES_POR_SESION: dict[str, Path] = {
    "2026-monaco-r": OPENF1_MONACO,
    "2026-australia-r": OPENF1_AUSTRALIA,
    "2026-sao-paulo-r": OPENF1_SAO_PAULO,
    "2026-barcelona-r": OPENF1_BARCELONA,
    "2026-hungria-r": OPENF1_HUNGRIA,
}


@dataclass(frozen=True)
class Corrida:
    """Todo lo que produce una corrida del pipeline sobre una sesión."""

    parquet: Path
    parquet_sha256: str
    warnings: tuple[str, ...]
    readings: tuple[Reading, ...]
    console: tuple[str, ...]


def correr_pipeline(session: str, trabajo: Path) -> Corrida:
    """Fixture a lecturas, escribiendo en `trabajo` (un directorio vacío)."""
    normalizado = normalizar_fixture(FIXTURES_POR_SESION[session], session, trabajo / "raw")
    parquet = trabajo / "canonical" / f"{session}.parquet"
    write_events(parquet, normalizado.meta, normalizado.events)
    replay = Replay.from_parquet(parquet, FakeClock(), speed=None, engine=Engine.default())
    printer = ConsolePrinter(replay.state)
    lecturas: list[Reading] = []
    consola: list[str] = []
    for lote in replay.run():
        consola += printer.lines(lote)
        lecturas += [lectura for paso in lote for lectura in paso.readings]
    return Corrida(
        parquet=parquet,
        parquet_sha256=hashlib.sha256(parquet.read_bytes()).hexdigest(),
        warnings=tuple(normalizado.warnings),
        readings=tuple(lecturas),
        console=tuple(consola),
    )


def lecturas_a_json(lecturas: tuple[Reading, ...] | list[Reading]) -> str:
    """Serialización estable: mismo contenido, mismos bytes. Termina con salto de línea.

    Un renglón por campo y por dato de evidencia, para que el diff de un golden se lea.
    """
    if not lecturas:
        return "[]\n"

    def dump(valor: object) -> str:
        return json.dumps(valor, ensure_ascii=False)

    bloques: list[str] = []
    for r in lecturas:
        evidencia = ",\n".join(
            "      "
            + dump({"name": e.name, "value": e.value, **({"unit": e.unit} if e.unit else {})})
            for e in r.evidence
        )
        bloques.append(
            "  {\n"
            f'    "rule": {dump(r.rule)},\n'
            f'    "key": {dump(r.key)},\n'
            f'    "t": {dump(r.t.isoformat())},\n'
            f'    "lap": {r.lap},\n'
            f'    "drivers": {dump(list(r.drivers))},\n'
            '    "evidence": [\n'
            f"{evidencia}\n"
            "    ],\n"
            f'    "text": {dump(r.text)}\n'
            "  }"
        )
    return "[\n" + ",\n".join(bloques) + "\n]\n"


def verificar_golden(nombre: str, obtenido: str, request: pytest.FixtureRequest) -> None:
    """Compara con tests/golden/<nombre>; con `--golden-update` lo reescribe."""
    destino = GOLDEN / nombre
    if request.config.getoption("--golden-update"):
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(obtenido, encoding="utf-8")
        return
    if not destino.exists():
        pytest.fail(
            f"falta el golden {destino.name}: revisar la salida y correr make golden-update"
        )
    esperado = destino.read_text(encoding="utf-8")
    assert obtenido == esperado, (
        f"la salida cambió respecto de {destino.name}. Si el cambio es intencional: "
        "make golden-update, revisar el diff completo y poner el motivo en el commit."
    )
