#!/usr/bin/env bash
# Verifica que la capa privada no quede versionada en el repo público (ADR 0008).
# Uso: make check-private
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
fail=0

# Con barra final: la regla /.private/ solo aplica a directorios y en un clon
# limpio (CI) la carpeta no existe, así que git no sabría que es un directorio.
if ! git check-ignore -q .private/; then
  echo "ERROR: .private/ no está ignorado. Falta la regla /.private/ en .gitignore."
  fail=1
fi

tracked="$(git ls-files -- .private CLAUDE.local.md)"
if [ -n "$tracked" ]; then
  echo "ERROR: archivos privados en el índice del repo público:"
  echo "$tracked"
  echo "Quitarlos con: git rm -r --cached <ruta>"
  fail=1
fi

gitlinks="$(git ls-files -s | awk '$1 == "160000" { print $4 }')"
if [ -n "$gitlinks" ]; then
  echo "ERROR: repositorios embebidos registrados en el repo público: $gitlinks"
  echo "Quitarlos con: git rm --cached <ruta>"
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "check-private: OK"
fi
exit "$fail"
