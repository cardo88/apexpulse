#!/usr/bin/env bash
# Hook Stop de Claude Code: corre make -s check-docs WARN=1 y devuelve los avisos al agente.
# Sale con 2 para que Claude Code muestre los avisos al agente y siga trabajando. Si el turno
# ya viene de un bloqueo de este hook (stop_hook_active), solo informa y deja terminar.
set -uo pipefail

entrada="$(cat)"
cd "$(dirname "$0")/.."

avisos="$(make -s check-docs WARN=1 2>&1 >/dev/null)"
[ -z "$avisos" ] && exit 0

if printf '%s' "$entrada" | grep -Eq '"stop_hook_active"[[:space:]]*:[[:space:]]*true'; then
  printf 'check-docs sigue con avisos:\n%s\n' "$avisos" >&2
  exit 0
fi

printf 'check-docs encontró avisos; resolverlos antes de terminar:\n%s\n' "$avisos" >&2
exit 2
