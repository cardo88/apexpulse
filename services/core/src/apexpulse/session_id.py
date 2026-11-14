"""Identificador de sesión `<año>-<circuito>-<tipo>` y tabla de circuitos.

Ejemplo: `2026-sao-paulo-r` es la carrera de 2026 en Interlagos. Los circuitos válidos
están en `config/circuits.toml`; cada uno declara el nombre que usa cada fuente.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import cache
from importlib import resources

PRIMER_ANIO = 2023  # alcance del MVP: temporadas 2023 en adelante

# Tipo de sesión del identificador -> nombres de sesión aceptados en OpenF1.
# "Sprint Shootout" es el nombre que usó OpenF1 en 2023.
SESSION_TYPES: dict[str, tuple[str, ...]] = {
    "r": ("Race",),
    "q": ("Qualifying",),
    "s": ("Sprint",),
    "sq": ("Sprint Qualifying", "Sprint Shootout"),
    "fp1": ("Practice 1",),
    "fp2": ("Practice 2",),
    "fp3": ("Practice 3",),
}

_RE_ID = re.compile(r"^(?P<anio>\d{4})-(?P<circuito>[a-z0-9]+(?:-[a-z0-9]+)*)-(?P<tipo>[a-z0-9]+)$")


class SessionIdError(ValueError):
    """El identificador de sesión no tiene el formato esperado o no existe el circuito."""


@dataclass(frozen=True)
class Circuit:
    """Circuito de la tabla `config/circuits.toml`."""

    slug: str
    nombre: str
    openf1: str  # circuit_short_name en OpenF1


@dataclass(frozen=True)
class SessionId:
    """Sesión identificada como `<año>-<circuito>-<tipo>`."""

    year: int
    circuit: str
    kind: str

    def __str__(self) -> str:
        return f"{self.year}-{self.circuit}-{self.kind}"

    @classmethod
    def parse(cls, texto: str) -> SessionId:
        """Valida el formato, el año, el tipo y que el circuito exista en la tabla."""
        coincidencia = _RE_ID.match(texto.strip())
        if not coincidencia:
            raise SessionIdError(
                f"'{texto}' no es un identificador válido. Formato: <año>-<circuito>-<tipo>, "
                "por ejemplo 2026-sao-paulo-r."
            )
        anio = int(coincidencia["anio"])
        circuito = coincidencia["circuito"]
        tipo = coincidencia["tipo"]
        if anio < PRIMER_ANIO:
            raise SessionIdError(f"{texto}: solo se admiten temporadas desde {PRIMER_ANIO}.")
        if tipo not in SESSION_TYPES:
            raise SessionIdError(
                f"{texto}: tipo '{tipo}' desconocido. Tipos válidos: {', '.join(SESSION_TYPES)}."
            )
        if circuito not in circuits():
            raise SessionIdError(
                f"{texto}: circuito '{circuito}' desconocido. Circuitos válidos: "
                f"{', '.join(sorted(circuits()))}. Para sumar uno, editar config/circuits.toml."
            )
        return cls(year=anio, circuit=circuito, kind=tipo)

    @property
    def circuit_info(self) -> Circuit:
        return circuits()[self.circuit]


@cache
def circuits() -> dict[str, Circuit]:
    """Carga la tabla de circuitos empaquetada con apexpulse."""
    texto = resources.files("apexpulse").joinpath("config/circuits.toml").read_text("utf-8")
    datos = tomllib.loads(texto)
    return {
        slug: Circuit(slug=slug, nombre=str(campos["nombre"]), openf1=str(campos["openf1"]))
        for slug, campos in datos["circuitos"].items()
    }
