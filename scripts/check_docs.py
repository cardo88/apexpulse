"""Verifica que la documentación y el CHANGELOG acompañen al cambio.

Uso: make check-docs. Con WARN=1 informa los problemas por stderr y sale con 0 (hook Stop).

Variables de entorno:
- BASE_REF: referencia contra la que se calcula el cambio. Por defecto origin/main o main.
- PR_BODY: cuerpo del PR; si declara "Docs: sin impacto, <motivo>" se omite la regla del
  CHANGELOG y la matriz.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import mapa

RAIZ = Path(__file__).resolve().parent.parent

LIMITES_DE_LINEAS = {
    "AGENTS.md": 120,
    "docs/ai/contexto.md": 200,
}

# Declaración válida: "Docs: sin impacto, " seguido de un motivo real (no el texto de la plantilla).
RE_SIN_IMPACTO = re.compile(r"Docs: sin impacto, (?!<motivo>)\S")
RE_ENLACE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
RE_ADR = re.compile(r"^docs/adr/\d{4}-.+\.md$")

# Archivos cuyo cambio no exige entrada en el CHANGELOG.
EXENTOS_DE_CHANGELOG = re.compile(r"^(CHANGELOG\.md|docs/ai/mapa-codigo\.md)$")


@dataclass(frozen=True)
class Regla:
    """Fila de la matriz del skill cambio-documentado."""

    patron: re.Pattern[str]
    documentos: tuple[str, ...]
    todos: bool = False  # True: exige todos los documentos; False: alcanza con uno.

    def describir(self) -> str:
        union = " y " if self.todos else " o "
        return union.join(self.documentos)


MATRIZ = (
    Regla(re.compile(r"^services/core/src/apexpulse/sources/"), ("docs/fuentes-de-datos.md",)),
    Regla(re.compile(r"^services/core/src/apexpulse/model/"), ("docs/modelo-de-eventos.md",)),
    Regla(
        re.compile(r"^services/core/src/apexpulse/(readings|messages/es)/"), ("docs/lecturas.md",)
    ),
    Regla(re.compile(r"^services/core/src/apexpulse/api/"), ("docs/arquitectura.md",)),
    Regla(re.compile(r"^web/src/styles/"), ("docs/diseno-visual.md",)),
    Regla(
        re.compile(r"^(Makefile|compose\.ya?ml|\.env\.example)$"),
        ("docs/setup-local.md", "AGENTS.md"),
    ),
    Regla(re.compile(r"^infra/"), ("docs/arquitectura.md", "docs/runbook.md")),
    Regla(RE_ADR, ("docs/adr/README.md", "docs/ai/contexto.md"), todos=True),
)


def _git(*args: str) -> str:
    resultado = subprocess.run(
        ["git", *args], cwd=RAIZ, capture_output=True, text=True, check=False
    )
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.strip() or f"git {' '.join(args)} falló")
    return resultado.stdout


def _base() -> str | None:
    candidatas = [os.environ["BASE_REF"]] if os.environ.get("BASE_REF") else ["origin/main", "main"]
    for referencia in candidatas:
        if set(referencia) <= {"0"}:
            return None  # push de una rama nueva: no hay base contra la cual comparar
        try:
            return _git("merge-base", referencia, "HEAD").strip()
        except RuntimeError:
            continue
    return None


def _archivos_cambiados(base: str | None) -> set[str]:
    cambiados: set[str] = set()
    if base:
        cambiados.update(_git("diff", "--name-only", f"{base}...HEAD").split())
    cambiados.update(_git("diff", "--name-only", "HEAD").split())
    cambiados.update(_git("ls-files", "--others", "--exclude-standard").split())
    return {ruta for ruta in cambiados if not ruta.startswith(".private/")}


def _declara_sin_impacto(base: str | None) -> bool:
    if RE_SIN_IMPACTO.search(os.environ.get("PR_BODY", "")):
        return True
    if base:
        return bool(RE_SIN_IMPACTO.search(_git("log", "--format=%B", f"{base}..HEAD")))
    return False


def revisar_limites() -> list[str]:
    problemas = []
    for ruta, limite in LIMITES_DE_LINEAS.items():
        archivo = RAIZ / ruta
        if archivo.exists():
            lineas = len(archivo.read_text(encoding="utf-8").splitlines())
            if lineas > limite:
                problemas.append(f"{ruta} tiene {lineas} líneas; el límite es {limite}.")
    return problemas


def revisar_enlaces() -> list[str]:
    problemas = []
    for ruta in _git("ls-files", "--cached", "--others", "--exclude-standard", "*.md").split():
        archivo = RAIZ / ruta
        if not archivo.exists():
            continue
        en_bloque = False
        for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            if linea.lstrip().startswith(("```", "~~~")):
                en_bloque = not en_bloque
            if en_bloque:
                continue
            for destino in RE_ENLACE.findall(linea):
                if re.match(r"^[a-z][a-z0-9+.-]*:", destino) or destino.startswith("#"):
                    continue
                objetivo = destino.split("#", 1)[0]
                if not (archivo.parent / objetivo).exists():
                    problemas.append(f"{ruta}:{numero}: enlace roto a {destino}")
    return problemas


def revisar_mapa() -> list[str]:
    destino = RAIZ / "docs" / "ai" / "mapa-codigo.md"
    actual = destino.read_text(encoding="utf-8") if destino.exists() else ""
    if actual != mapa.generar():
        return ["docs/ai/mapa-codigo.md está desactualizado. Correr: make mapa"]
    return []


def revisar_cambio(base: str | None, cambiados: set[str]) -> list[str]:
    if not cambiados or _declara_sin_impacto(base):
        return []
    problemas = []
    if "CHANGELOG.md" not in cambiados and any(
        not EXENTOS_DE_CHANGELOG.match(ruta) for ruta in cambiados
    ):
        problemas.append("Falta la entrada en CHANGELOG.md, sección [Unreleased].")
    for regla in MATRIZ:
        disparadores = sorted(ruta for ruta in cambiados if regla.patron.match(ruta))
        if not disparadores:
            continue
        tocados = [doc for doc in regla.documentos if doc in cambiados]
        cumple = len(tocados) == len(regla.documentos) if regla.todos else bool(tocados)
        if not cumple:
            problemas.append(f"Cambió {', '.join(disparadores)}: actualizar {regla.describir()}.")
    return problemas


def main() -> int:
    solo_avisar = os.environ.get("WARN", "") not in ("", "0")
    base = _base()
    cambiados = _archivos_cambiados(base)
    problemas = [
        *revisar_limites(),
        *revisar_enlaces(),
        *revisar_mapa(),
        *revisar_cambio(base, cambiados),
    ]
    if not problemas:
        if not solo_avisar:
            print("check-docs: OK")
        return 0
    titulo = "AVISO" if solo_avisar else "ERROR"
    for problema in problemas:
        print(f"{titulo}: {problema}", file=sys.stderr)
    if not solo_avisar:
        print(
            "Si el cambio no afecta documentación, declararlo en el commit o el PR: "
            '"Docs: sin impacto, <motivo>". Ver el skill cambio-documentado.',
            file=sys.stderr,
        )
    return 0 if solo_avisar else 1


if __name__ == "__main__":
    raise SystemExit(main())
