"""Recorte de una sesión de OpenF1 a una ventana, para armar fixtures versionados.

Parte del crudo de data/raw (`make fetch`) y escribe los `<endpoint>.json` que sirve el OpenF1
simulado de los tests, sin modificar ningún registro. Criterio por endpoint:

- `pit`, `race_control` y `weather`: registros con `date` dentro de la ventana de tiempo.
- `laps`: vueltas del rango pedido, más la última completada antes de la ventana de cada piloto
  (deja bien el contador de vuelta al llegar a ella) y las filas que hacen falta para fechar los
  stints (ver abajo).
- `position`, `intervals`: registros dentro de la ventana, más, por piloto, el último anterior a
  ella y el último anterior al inicio de la sesión. OpenF1 publica estos endpoints solo cuando el
  valor cambia: sin esos registros, el recorte no sabe quién lidera ni a qué distancia está cada
  auto hasta que haya un cambio.
- `stints`: los que se superponen con el rango de vueltas (incluye el stint en curso de cada piloto
  al empezar la ventana) y el último anterior de cada piloto, para los que abandonaron antes. El
  normalizador fecha un stint con la fila de `laps` de su
  `lap_start`; si esa vuelta quedó fuera del rango, se suma la fila (y nada más de esa vuelta).
- `drivers`: todos, sin recorte.
- `sessions`: las sesiones del mismo fin de semana (`meeting_key`).
- `vaciar`: endpoints que se escriben vacíos, aunque tengan datos en la ventana.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from apexpulse.session_id import SessionId
from apexpulse.sources.base import SourceError
from apexpulse.sources.rawstore import read_jsonl_zst

Registro = dict[str, Any]


@dataclass(frozen=True)
class Ventana:
    """Tramo a conservar: instantes UTC (`desde` incluido, `hasta` incluido) y vueltas."""

    desde: datetime
    hasta: datetime
    vuelta_desde: int
    vuelta_hasta: int

    def __post_init__(self) -> None:
        for instante in (self.desde, self.hasta):
            if instante.tzinfo is None:
                raise ValueError("la ventana necesita instantes con zona horaria")
        if self.hasta < self.desde:
            raise ValueError("hasta es anterior a desde")
        if self.vuelta_hasta < self.vuelta_desde:
            raise ValueError("la vuelta final es anterior a la inicial")


def _fecha(fila: Registro) -> datetime:
    return datetime.fromisoformat(str(fila["date"]))


def _en_ventana(filas: list[Registro], ventana: Ventana) -> list[Registro]:
    return [f for f in filas if ventana.desde <= _fecha(f) <= ventana.hasta]


def _con_ultimo_previo(
    filas: list[Registro],
    ventana: Ventana,
    inicio_sesion: datetime,
    *,
    valido: Callable[[Registro], bool] = lambda _: True,
) -> list[Registro]:
    """Filas de la ventana más, por piloto, la última válida anterior a cada corte.

    Hay dos cortes: el inicio de la ventana, que da el estado correcto al llegar a ella, y el inicio
    de la sesión, que es donde empieza el replay y da el estado de arranque (por ejemplo, quién
    lidera en la primera línea de la consola). Conserva el orden del crudo.
    """
    previas: set[int] = set()
    for corte in {inicio_sesion, ventana.desde}:
        ultimo: dict[int, Registro] = {}
        for fila in filas:
            if _fecha(fila) < corte and valido(fila):
                ultimo[int(fila["driver_number"])] = fila
        previas |= {id(f) for f in ultimo.values()}
    return [f for f in filas if id(f) in previas or ventana.desde <= _fecha(f) <= ventana.hasta]


def _con_distancia(fila: Registro) -> bool:
    """El normalizador descarta los intervalos sin ninguna distancia: no sirven de arrastre."""
    return fila.get("gap_to_leader") is not None or fila.get("interval") is not None


def _stints(filas: list[Registro], ventana: Ventana) -> list[Registro]:
    """Stints que se superponen con las vueltas, más el último anterior de cada piloto.

    El último anterior cubre a los pilotos que abandonaron antes del rango: su último stint
    sigue en el estado de la sesión completa.
    """
    ultimo_previo: dict[int, int] = {}  # piloto -> stint_number más alto que empezó antes
    for fila in filas:
        if fila["lap_start"] < ventana.vuelta_desde:
            piloto = int(fila["driver_number"])
            ultimo_previo[piloto] = max(ultimo_previo.get(piloto, 0), int(fila["stint_number"]))
    elegidos = []
    for fila in filas:
        fin = fila.get("lap_end")
        se_superpone = fila["lap_start"] <= ventana.vuelta_hasta and (
            fin is None or fin >= ventana.vuelta_desde
        )
        es_ultimo_previo = ultimo_previo.get(int(fila["driver_number"])) == fila["stint_number"]
        if se_superpone or es_ultimo_previo:
            elegidos.append(fila)
    return elegidos


def _fin_de_vuelta(fila: Registro, siguiente: Registro | None) -> datetime | None:
    """Instante en que termina la vuelta, como lo calcula el normalizador; None si no se sabe."""
    if fila["date_start"] is None:
        return None
    inicio = datetime.fromisoformat(str(fila["date_start"]))
    if fila["lap_duration"] is not None:
        return inicio + timedelta(seconds=float(fila["lap_duration"]))
    if siguiente is not None and siguiente["date_start"] is not None:
        return datetime.fromisoformat(str(siguiente["date_start"]))
    return None


def _laps(filas: list[Registro], stints: list[Registro], ventana: Ventana) -> list[Registro]:
    """Vueltas del rango, la última completada antes de la ventana y las que fechan los stints.

    La última completada antes de `desde` de cada piloto deja el contador de vuelta de la sesión
    (máximo de vueltas completadas) en el valor correcto al llegar a la ventana.
    """
    por_piloto: dict[int, dict[int, Registro]] = {}
    for fila in filas:
        por_piloto.setdefault(int(fila["driver_number"]), {})[int(fila["lap_number"])] = fila
    necesarias = {(int(s["driver_number"]), int(s["lap_start"])) for s in stints}
    for piloto, vueltas in por_piloto.items():
        for numero in sorted(vueltas, reverse=True):
            fin = _fin_de_vuelta(vueltas[numero], vueltas.get(numero + 1))
            if fin is not None and fin < ventana.desde:
                necesarias.add((piloto, numero))
                break
    return [
        f
        for f in filas
        if ventana.vuelta_desde <= f["lap_number"] <= ventana.vuelta_hasta
        or (int(f["driver_number"]), int(f["lap_number"])) in necesarias
    ]


def recortar_openf1(
    raw: Path, destino: Path, ventana: Ventana, *, vaciar: frozenset[str] = frozenset()
) -> dict[str, int]:
    """Escribe los JSON recortados en `destino` y devuelve los registros por archivo.

    `raw` es data/raw/<año>/<sesion>/openf1, que tiene que estar completo (con manifest.json).
    `vaciar` nombra endpoints que se escriben como lista vacía: sirve para un fixture de carrera
    completa sin los endpoints pesados (`intervals`) que una prueba no necesita.
    """
    manifiesto = raw / "manifest.json"
    if not manifiesto.exists():
        raise SourceError(f"no hay crudo completo en {raw}: correr make fetch")
    datos = json.loads(manifiesto.read_text(encoding="utf-8"))

    def leer(endpoint: str) -> list[Registro]:
        return list(read_jsonl_zst(raw / datos["endpoints"][endpoint]["file"]))

    inicio = datetime.fromisoformat(datos["openf1_session"]["date_start"])
    stints = _stints(leer("stints"), ventana)
    salida: dict[str, list[Registro]] = {
        "drivers": leer("drivers"),
        "laps": _laps(leer("laps"), stints, ventana),
        "stints": stints,
        "pit": _en_ventana(leer("pit"), ventana),
        "position": _con_ultimo_previo(leer("position"), ventana, inicio),
        "intervals": _con_ultimo_previo(leer("intervals"), ventana, inicio, valido=_con_distancia),
        "race_control": _en_ventana(leer("race_control"), ventana),
        "weather": _en_ventana(leer("weather"), ventana),
        "sessions": _sesiones(raw, datos),
    }
    desconocidos = vaciar - set(salida)
    if desconocidos:
        raise SourceError(f"endpoints desconocidos en vaciar: {sorted(desconocidos)}")
    for endpoint in vaciar:
        salida[endpoint] = []
    destino.mkdir(parents=True, exist_ok=True)
    for endpoint, filas in salida.items():
        texto = _json_por_linea(filas)
        (destino / f"{endpoint}.json").write_text(texto, encoding="utf-8")
    return {endpoint: len(filas) for endpoint, filas in salida.items()}


def _json_por_linea(filas: list[Registro]) -> str:
    """Un registro por línea: el diff de git se lee por registro y el archivo pesa menos."""
    if not filas:
        return "[]\n"
    cuerpo = ",\n".join(json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in filas)
    return f"[\n{cuerpo}\n]\n"


def _sesiones(raw: Path, datos: dict[str, Any]) -> list[Registro]:
    """Sesiones del mismo fin de semana, desde la caché de `sessions` del año."""
    meeting = datos["openf1_session"]["meeting_key"]
    año = SessionId.parse(datos["session"]).year
    cache = raw.parents[1] / "_openf1" / "sessions.jsonl.zst"
    if not cache.exists():
        raise SourceError(f"falta la caché de sessions de {año}: {cache}")
    return [f for f in read_jsonl_zst(cache) if f["meeting_key"] == meeting]
