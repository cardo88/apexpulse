"""Verifica el formato de los skills y su correspondencia con la tabla de AGENTS.md.

Uso: make check-skills.

Reglas (formato Agent Skills, ADR 0006):
- Cada carpeta de .claude/skills/ tiene SKILL.md con frontmatter `name` y `description`.
- `name` coincide con la carpeta, en kebab-case y con 64 caracteres como máximo.
- `description` no está vacía y tiene 1024 caracteres como máximo.
- SKILL.md tiene 500 líneas como máximo y una sección "## Fuente de verdad".
- La tabla "## Skills" de AGENTS.md lista cada skill existente con estado "Activo", y todo
  skill marcado "Activo" tiene su carpeta.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
AGENTS = RAIZ / "AGENTS.md"

RE_NOMBRE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_LINEAS = 500


def _frontmatter(texto: str) -> dict[str, str] | None:
    lineas = texto.splitlines()
    if not lineas or lineas[0].strip() != "---":
        return None
    campos: dict[str, str] = {}
    for linea in lineas[1:]:
        if linea.strip() == "---":
            return campos
        if ":" in linea and not linea.startswith((" ", "\t")):
            clave, valor = linea.split(":", 1)
            campos[clave.strip()] = valor.strip().strip("\"'")
    return None


def revisar_skill(carpeta: Path) -> list[str]:
    nombre = carpeta.name
    archivo = carpeta / "SKILL.md"
    if not archivo.exists():
        return [f"{nombre}: falta SKILL.md"]
    texto = archivo.read_text(encoding="utf-8")
    campos = _frontmatter(texto)
    if campos is None:
        return [f"{nombre}: SKILL.md no empieza con un frontmatter YAML entre líneas ---"]
    problemas = []
    declarado = campos.get("name", "")
    if declarado != nombre:
        problemas.append(f"{nombre}: name es '{declarado}'; debe coincidir con la carpeta")
    if not RE_NOMBRE.match(nombre) or len(nombre) > 64:
        problemas.append(f"{nombre}: el nombre debe ser kebab-case de 64 caracteres o menos")
    descripcion = campos.get("description", "")
    if not descripcion:
        problemas.append(f"{nombre}: falta description en el frontmatter")
    elif len(descripcion) > 1024:
        problemas.append(f"{nombre}: description tiene {len(descripcion)} caracteres (máx. 1024)")
    lineas = len(texto.splitlines())
    if lineas > MAX_LINEAS:
        problemas.append(f"{nombre}: SKILL.md tiene {lineas} líneas (máx. {MAX_LINEAS})")
    if "\n## Fuente de verdad" not in texto:
        problemas.append(f"{nombre}: falta la sección '## Fuente de verdad'")
    return problemas


def _tabla_agents() -> dict[str, str]:
    """Devuelve {skill: estado} a partir de la tabla '## Skills' de AGENTS.md."""
    tabla: dict[str, str] = {}
    en_seccion = False
    for linea in AGENTS.read_text(encoding="utf-8").splitlines():
        if linea.startswith("## "):
            en_seccion = linea.strip() == "## Skills"
            continue
        if not en_seccion or not linea.startswith("|"):
            continue
        celdas = [celda.strip() for celda in linea.strip().strip("|").split("|")]
        if len(celdas) < 3 or celdas[0] == "Skill" or set(celdas[0]) <= {"-", " "}:
            continue
        tabla[celdas[0]] = celdas[-1]
    return tabla


def revisar_agents(existentes: set[str]) -> list[str]:
    tabla = _tabla_agents()
    if not tabla:
        return ["AGENTS.md: no se encontró la tabla de la sección '## Skills'"]
    problemas = []
    for nombre in sorted(existentes):
        estado = tabla.get(nombre)
        if estado is None:
            problemas.append(f"AGENTS.md: falta el skill '{nombre}' en la tabla de skills")
        elif estado != "Activo":
            problemas.append(
                f"AGENTS.md: el skill '{nombre}' existe pero figura como '{estado}'; "
                "cambiarlo a 'Activo'"
            )
    for nombre, estado in sorted(tabla.items()):
        if estado == "Activo" and nombre not in existentes:
            problemas.append(
                f"AGENTS.md: '{nombre}' figura como Activo pero no existe .claude/skills/{nombre}/"
            )
    return problemas


def main() -> int:
    carpetas = sorted(p for p in SKILLS.iterdir() if p.is_dir()) if SKILLS.exists() else []
    problemas: list[str] = []
    for carpeta in carpetas:
        problemas += revisar_skill(carpeta)
    problemas += revisar_agents({c.name for c in carpetas})
    if problemas:
        for problema in problemas:
            print(f"ERROR: {problema}", file=sys.stderr)
        return 1
    print(f"check-skills: OK ({len(carpetas)} skills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
