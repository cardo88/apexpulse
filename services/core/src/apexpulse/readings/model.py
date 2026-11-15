"""Modelo de una lectura: una conclusión con su evidencia numérica y su texto en español.

Es el contrato entre el motor y quien muestre las lecturas (consola ahora, API en H3). No es parte
del modelo canónico de eventos: lo produce el motor a partir de ellos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

Valor = float | int | str


@dataclass(frozen=True)
class Evidence:
    """Un dato observado que sostiene la lectura, con nombre y unidad (`s`, `vueltas`, ...)."""

    name: str
    value: Valor
    unit: str = ""


@dataclass(frozen=True)
class Reading:
    """Conclusión de una regla.

    - `key`: identifica la lectura de forma estable (dedupe y golden); no depende del texto.
    - `t`: instante del evento que la emite, que es cuando la información está disponible.
    - `lap`: vuelta del líder en la pasada o la situación que describe el texto.
    - `drivers`: números de auto; el primero es el protagonista.
    """

    rule: str
    key: str
    t: datetime
    lap: int
    drivers: tuple[int, ...]
    evidence: tuple[Evidence, ...]
    text: str

    def evidence_value(self, name: str) -> Valor:
        for item in self.evidence:
            if item.name == name:
                return item.value
        raise KeyError(name)
