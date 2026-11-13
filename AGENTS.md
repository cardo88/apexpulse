# ApexPulse: instrucciones para agentes

Proyecto personal y no oficial: lectura de carrera de F1 en español
(interpretación del timing) y análisis post-carrera. Sin monetización.
Ver DISCLAIMER.md.

## Antes de empezar
1. Si existe .private/estado.md, leerlo: hito actual y próximo paso.
   Si no existe, el estado público está en docs/roadmap.md.
2. Para cambios que cruzan componentes, leer docs/ai/contexto.md.
3. Para ubicar código, usar docs/ai/mapa-codigo.md (desde H1 tarea 3)
   en lugar de recorrer el árbol.

## Mapa
- services/core/: Python. Fuentes, modelo canónico, replay, motor de lecturas, API.
- web/: Astro + Svelte. Vista "En carrera" y post-carrera (desde H3).
- fixtures/sessions/: sesiones recortadas para tests, versionadas.
- data/: datos locales, ignorado por git.
- docs/: documentación. docs/adr/ para decisiones, docs/ai/ para agentes.
- scripts/: verificaciones que corre make.
- infra/: Terraform y nodo propio (fase 3).
- .private/: capa privada del autor. Repo git independiente, ignorado por el
  repo público (ADR 0008). Puede no existir.

## Comandos
Todo se ejecuta por make. La columna "Desde" indica cuándo existe cada target.

| Comando                            | Qué hace                                       | Desde      |
|------------------------------------|------------------------------------------------|------------|
| make check                         | Todas las verificaciones                       | Disponible |
| make check-private                 | Falla si algo privado quedó versionado         | Disponible |
| make setup                         | Instala dependencias y hooks                   | H1 t3      |
| make check-docs / check-skills     | Docs y skills al día con el cambio             | H1 t3      |
| make mapa                          | Regenera docs/ai/mapa-codigo.md                | H1 t3      |
| make fetch SESSION=<id>            | Descarga y cachea una sesión                   | H1 t4      |
| make normalize SESSION=<id>        | Genera eventos canónicos                       | H1 t5      |
| make replay SESSION=<id> SPEED=<n> | Reproduce y muestra lecturas                   | H1 t6      |
| make golden SESSION=<id>           | Regenera la salida esperada (revisar el diff)  | H1 t8      |
| docker compose up                  | core en :8000, web en :4321                    | H3         |

## Reglas no negociables
- Todo cambio actualiza la documentación afectada y el CHANGELOG en el mismo
  cambio. Si no aplica, el PR declara "Docs: sin impacto, <motivo>".
  Ver el skill cambio-documentado.
- Documentación en español, técnica, sin emoticones, con ejemplos reales.
- Nunca versionar .private/ ni CLAUDE.local.md en el repo público, ni copiar
  su contenido a archivos, commits, issues o PRs públicos.
- Nunca conectar servicios en la nube directo a F1 Live Timing ni a su
  archivo estático (bloqueo de IPs de cloud).
- Nunca usar credenciales de F1 TV ni publicar datos crudos del feed; solo
  datos derivados.
- Sin logos, tipografías ni nombres oficiales de F1 en la UI; mantener el
  disclaimer.
- No copiar código de proyectos con licencia incompatible (AGPL, GPL).
- Las lecturas son determinísticas: misma entrada, misma salida. Cambios de
  texto o de umbral pasan por golden tests.
- Secretos solo en variables de entorno o en el gestor de secretos.

## Skills
| Skill               | Para qué                                             | Estado   |
|---------------------|------------------------------------------------------|----------|
| cambio-documentado  | Cerrar cualquier cambio con docs, CHANGELOG y estado | Activo   |
| nuevo-adr           | Registrar una decisión                               | Activo   |
| sesion-replay       | Descargar, recortar y reproducir sesiones; golden    | Activo   |
| nueva-lectura       | Agregar o ajustar una regla del motor                | H1 t7    |
| fuente-de-datos     | Fuente nueva o cambio de esquema del feed            | H1 t4    |
| ui-componente       | Vistas y componentes con los tokens del proyecto     | H3       |
| post-carrera        | Generar y revisar el análisis de una sesión (manual) | H4       |
| release             | Cortar una versión (manual)                          | H5       |
| infra-nube          | Terraform y despliegue                               | H6       |

## Al terminar una sesión de trabajo
Si existe .private/estado.md, actualizarlo (qué se hizo, qué quedó pendiente
y el próximo paso) y commitearlo en el repo privado con git -C .private.
