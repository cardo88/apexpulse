# 0008. La información privada vive en un repo anidado en .private/

- Estado: Aceptado
- Fecha: 2026-11-12

## Contexto

El repositorio es público desde el primer commit. Parte de la información del proyecto no debe publicarse: el plan con supuestos personales, la bitácora de trabajo, notas y borradores, y la operación del nodo propio de H7 (hostnames, IP, configuración del túnel), que expondría la red doméstica. Lo que entra en el historial de un repo público no se puede retirar de forma confiable, porque pudo ser clonado o copiado.

## Decisión

- El repo público ignora `/.private/` desde antes de su primer commit.
- `.private/` es un repositorio git independiente con remoto privado (`apexpulse-private`).
- `CLAUDE.local.md`, también ignorado, importa `.private/contexto-privado.md` para que Claude Code cargue el contexto privado sin que el repo público dependa de él.
- `make check-private` falla si algún archivo privado está en el índice del repo público o si hay un repositorio embebido registrado.

## Alternativas descartadas

- Todo público: expone la red doméstica y el razonamiento en borrador.
- Dos repos completos con código duplicado: doble mantenimiento, rompe la regla de documentar en el mismo cambio y CI no ve el otro repo.
- Submódulo de git: publica la URL del repo privado en `.gitmodules` y los clones recursivos fallan por falta de acceso.
- Repo privado con espejo público filtrado: el historial público queda artificial y un error de filtro publica todo.

## Consecuencias

- En la compu, Claude Code ve ambas capas. En la web o en GitHub Actions solo ve la pública.
- Hay dos repos donde commitear: los cambios privados se hacen con `git -C .private`.
- La capa privada necesita su propio remoto como respaldo.
- Las herramientas que respetan `.gitignore` pueden saltear `.private/` en sus búsquedas: sus archivos se referencian por ruta explícita.
- Un repo privado no es un gestor de secretos: las credenciales siguen fuera de ambos repos.
