@AGENTS.md

## Solo para Claude Code
- El contexto privado del autor se carga desde CLAUDE.local.md (ignorado por
  git), que importa .private/contexto-privado.md. Si no existe, trabajar solo
  con lo público.
- Las búsquedas pueden saltear .private/ porque está ignorada: leer sus
  archivos por ruta explícita.
- Usar plan mode para cambios en services/core/src/apexpulse/model/ (contrato
  del modelo canónico) y en infra/.
- Desde H1 tarea 3 existe un hook Stop que corre "make -s check-docs WARN=1".
  Si avisa, resolverlo antes de dar la tarea por terminada.
- En tareas largas, dejar el progreso en .private/estado.md antes de que se
  compacte el contexto.
