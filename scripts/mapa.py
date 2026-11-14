"""Genera docs/ai/mapa-codigo.md a partir de los docstrings, los scripts y el Makefile.

Uso: make mapa. Con --stdout imprime el mapa sin escribir el archivo (lo usa check-docs).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "docs" / "ai" / "mapa-codigo.md"
CORE_SRC = RAIZ / "services" / "core" / "src"
CORE_TESTS = RAIZ / "services" / "core" / "tests"
SCRIPTS = RAIZ / "scripts"
MAKEFILE = RAIZ / "Makefile"

SIN_DESCRIPCION = "(sin descripción)"
RE_TARGET = re.compile(r"^([A-Za-z0-9_-]+):[^=]*?##\s*(.+)$")


def _primera_linea_docstring(ruta: Path) -> str:
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    doc = ast.get_docstring(arbol)
    if not doc:
        return SIN_DESCRIPCION
    return doc.strip().splitlines()[0]


def _primera_linea_comentario(ruta: Path) -> str:
    for linea in ruta.read_text(encoding="utf-8").splitlines()[1:]:
        if linea.startswith("#"):
            texto = linea.lstrip("#").strip()
            if texto:
                return texto
        elif linea.strip():
            break
    return SIN_DESCRIPCION


def _celda(texto: str) -> str:
    return texto.replace("|", "\\|")


def _modulos_python(base: Path) -> list[tuple[str, str]]:
    filas: list[tuple[str, str]] = []
    for ruta in sorted(base.rglob("*.py")):
        relativa = ruta.relative_to(base)
        if any(parte.startswith(".") or parte == "__pycache__" for parte in relativa.parts):
            continue
        partes = list(relativa.with_suffix("").parts)
        if partes[-1] == "__init__":
            partes.pop()
        nombre = ".".join(partes) if partes else str(relativa)
        filas.append((nombre, _primera_linea_docstring(ruta)))
    return filas


def _scripts() -> list[tuple[str, str]]:
    filas: list[tuple[str, str]] = []
    for ruta in sorted(SCRIPTS.iterdir()):
        if ruta.suffix == ".py":
            filas.append((f"scripts/{ruta.name}", _primera_linea_docstring(ruta)))
        elif ruta.suffix == ".sh":
            filas.append((f"scripts/{ruta.name}", _primera_linea_comentario(ruta)))
    return filas


def _targets_make() -> list[tuple[str, str]]:
    filas: list[tuple[str, str]] = []
    for linea in MAKEFILE.read_text(encoding="utf-8").splitlines():
        coincidencia = RE_TARGET.match(linea)
        if coincidencia:
            filas.append((f"make {coincidencia.group(1)}", coincidencia.group(2).strip()))
    return filas


def _tabla(encabezado: tuple[str, str], filas: list[tuple[str, str]]) -> list[str]:
    lineas = [f"| {encabezado[0]} | {encabezado[1]} |", "|---|---|"]
    lineas += [f"| `{_celda(a)}` | {_celda(b)} |" for a, b in filas]
    return lineas


def generar() -> str:
    """Devuelve el contenido completo del mapa; la salida es determinística."""
    lineas = [
        "# Mapa de código",
        "",
        "Generado por `make mapa` (scripts/mapa.py) a partir de los docstrings de módulo, "
        "los comentarios de cabecera de scripts/ y los comentarios `##` del Makefile. "
        "No editar a mano: `make check-docs` falla si queda desactualizado.",
        "",
        "## services/core: paquete apexpulse",
        "",
        *_tabla(("Módulo", "Descripción"), _modulos_python(CORE_SRC)),
        "",
        "## services/core: tests",
        "",
        *_tabla(("Módulo", "Descripción"), _modulos_python(CORE_TESTS)),
        "",
        "## scripts",
        "",
        *_tabla(("Archivo", "Descripción"), _scripts()),
        "",
        "## Targets de make",
        "",
        *_tabla(("Comando", "Descripción"), _targets_make()),
        "",
    ]
    return "\n".join(lineas)


def main() -> int:
    contenido = generar()
    if "--stdout" in sys.argv[1:]:
        sys.stdout.write(contenido)
        return 0
    DESTINO.write_text(contenido, encoding="utf-8")
    print(f"mapa: {DESTINO.relative_to(RAIZ)} actualizado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
