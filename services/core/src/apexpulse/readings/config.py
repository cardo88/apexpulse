"""Carga y validación de config/readings.toml y config/mensajes_es.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib import resources
from typing import Any

from apexpulse.model import Compound, TrackStatus


class ConfigError(ValueError):
    """La configuración del motor de lecturas es inválida."""


@dataclass(frozen=True)
class StopsConfig:
    calibrated: bool
    confirm_timeout_laps: int


@dataclass(frozen=True)
class UndercutConfig:
    calibrated: bool
    max_gap_s: float
    min_tyre_age_laps: int
    confirm_laps: int
    recent_stop_laps: int
    min_lap: int
    min_vueltas_restantes: int


@dataclass(frozen=True)
class ReadingsConfig:
    stops: StopsConfig
    undercut: UndercutConfig


def _toml(nombre: str) -> dict[str, Any]:
    texto = resources.files("apexpulse").joinpath(f"config/{nombre}").read_text("utf-8")
    return tomllib.loads(texto)


def _seccion(datos: dict[str, Any], nombre: str, campos: dict[str, type]) -> dict[str, Any]:
    seccion = datos.get(nombre)
    if not isinstance(seccion, dict):
        raise ConfigError(f"readings.toml: falta la sección [{nombre}]")
    sobrantes = set(seccion) - set(campos)
    faltantes = set(campos) - set(seccion)
    if sobrantes or faltantes:
        raise ConfigError(
            f"readings.toml [{nombre}]: claves desconocidas {sorted(sobrantes)}"
            f" o faltantes {sorted(faltantes)}"
        )
    for clave, tipo in campos.items():
        valor = seccion[clave]
        valido = isinstance(valor, int | float) if tipo is float else type(valor) is tipo
        if not valido:
            raise ConfigError(f"readings.toml [{nombre}] {clave}: se esperaba {tipo.__name__}")
    return seccion


def load_config(datos: dict[str, Any] | None = None) -> ReadingsConfig:
    """Lee la configuración empaquetada (o `datos`, para los tests) y valida los rangos."""
    datos = _toml("readings.toml") if datos is None else datos
    s = _seccion(datos, "stops", {"calibrated": bool, "confirm_timeout_laps": int})
    u = _seccion(
        datos,
        "undercut_window",
        {
            "calibrated": bool,
            "max_gap_s": float,
            "min_tyre_age_laps": int,
            "confirm_laps": int,
            "recent_stop_laps": int,
            "min_lap": int,
            "min_vueltas_restantes": int,
        },
    )
    if s["confirm_timeout_laps"] < 1:
        raise ConfigError("readings.toml [stops] confirm_timeout_laps: mínimo 1")
    if u["max_gap_s"] <= 0:
        raise ConfigError("readings.toml [undercut_window] max_gap_s: tiene que ser mayor que 0")
    for clave in ("min_tyre_age_laps", "confirm_laps", "min_lap"):
        if u[clave] < 1:
            raise ConfigError(f"readings.toml [undercut_window] {clave}: mínimo 1")
    if u["recent_stop_laps"] < 0:
        raise ConfigError("readings.toml [undercut_window] recent_stop_laps: no puede ser negativo")
    if u["min_vueltas_restantes"] < 0:
        raise ConfigError(
            "readings.toml [undercut_window] min_vueltas_restantes: no puede ser negativo"
        )
    return ReadingsConfig(
        stops=StopsConfig(s["calibrated"], s["confirm_timeout_laps"]),
        undercut=UndercutConfig(
            u["calibrated"],
            float(u["max_gap_s"]),
            u["min_tyre_age_laps"],
            u["confirm_laps"],
            u["recent_stop_laps"],
            u["min_lap"],
            u["min_vueltas_restantes"],
        ),
    )


@dataclass(frozen=True)
class Messages:
    """Plantillas de texto en español."""

    templates: dict[str, dict[str, str]]
    fragments: dict[str, str]
    states: dict[str, str]
    compounds: dict[str, str]

    def render(self, regla: str, clave: str, **params: str) -> str:
        return self.templates[regla][clave].format(**params)

    def fragment(self, clave: str, **params: str) -> str:
        return self.fragments[clave].format(**params)


def load_messages(datos: dict[str, Any] | None = None) -> Messages:
    """Lee los textos empaquetados (o `datos`); verifica que cubran estados y compuestos."""
    datos = _toml("mensajes_es.toml") if datos is None else datos
    fragmentos = dict(datos["fragmentos"])
    estados = dict(datos["estados"])
    compuestos = dict(datos["compuestos"])
    plantillas = {
        k: dict(v) for k, v in datos.items() if k not in {"fragmentos", "estados", "compuestos"}
    }
    sin_estado = {e.value for e in TrackStatus} - {"GREEN", "RED", "FINISHED"} - set(estados)
    sin_compuesto = {c.value for c in Compound} - set(compuestos)
    if sin_estado or sin_compuesto:
        raise ConfigError(
            f"mensajes_es.toml: faltan estados {sorted(sin_estado)}"
            f" o compuestos {sorted(sin_compuesto)}"
        )
    return Messages(plantillas, fragmentos, estados, compuestos)
