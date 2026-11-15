"""Formato de números de los textos: coma decimal."""

from __future__ import annotations


def num(valor: float, decimales: int = 1) -> str:
    """`8.6` -> `"8,6"`."""
    return f"{valor:.{decimales}f}".replace(".", ",")
