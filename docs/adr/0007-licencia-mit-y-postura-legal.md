# 0007. Licencia MIT y postura legal de proyecto no oficial

- Estado: Aceptado
- Fecha: 2026-11-09

## Contexto

El repositorio es público desde el primer commit. Sin una licencia explícita, el código queda con todos los derechos reservados y nadie puede reutilizarlo legalmente. Además, el proyecto usa datos de terceros y se refiere a marcas registradas de F1.

## Decisión

- El código se publica con licencia MIT: cualquiera puede usarlo, modificarlo y redistribuirlo, con la única condición de conservar el aviso de copyright, y sin garantía.
- DISCLAIMER.md declara el carácter no oficial y sin fines comerciales.
- El nombre del proyecto no incluye "F1"; la UI no usa logos ni tipografías oficiales.
- Solo se publican datos derivados; nunca el crudo del feed ni audio de radio.
- No se usan credenciales de F1 TV.
- No se copia código de proyectos con licencias incompatibles, como f1-dash (AGPL-3.0).
- Un pedido de baja se atiende en un plazo máximo de 7 días.

## Alternativas descartadas

- Apache-2.0: equivalente en lo práctico, con texto más largo y una cláusula de patentes que este proyecto no necesita.
- AGPL-3.0: obliga a publicar el código de cualquier servicio derivado y reduce la reutilización.
- Sin licencia: impide que otros reutilicen el código aunque el repositorio sea público.

## Consecuencias

- Terceros pueden reutilizar el código, incluso con fines comerciales, manteniendo el aviso.
- La licencia no cubre datos ni marcas de terceros, que mantienen sus propios términos.
