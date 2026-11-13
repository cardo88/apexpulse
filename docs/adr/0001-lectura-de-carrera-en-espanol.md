# 0001. El producto es una lectura de carrera en español

- Estado: Aceptado
- Fecha: 2026-11-09

## Contexto

Existen varios dashboards de live timing (F1 Cosmos, f1-dash, F1 Pitwall, entre otros) centrados en mostrar datos crudos. Competir con más datos en tiempo real no aporta. El proyecto es personal, sin monetización, y sirve como portfolio técnico. Los principios, en orden de peso, son: identidad visual propia, diferenciación sostenida y un MVP chico que funcione.

## Decisión

ApexPulse muestra conclusiones con evidencia en español ("lecturas"): ventana de undercut, parada barata bajo Safety Car, degradación, batallas y cambios de condiciones. Se complementa con un análisis post-carrera de una página. La audiencia inicial son aficionados hispanohablantes que siguen la carrera como segunda pantalla.

## Alternativas descartadas

- Overlays para streamers (OBS): depende del vivo desde el día 1 y tiene mayor exposición pública.
- Pronósticos con track record: el track record necesita una temporada completa para tener valor.

## Consecuencias

- El MVP se puede construir y mostrar sin vivo.
- Las lecturas se emiten con un contrato JSON versionado, para que los overlays sean otra presentación del mismo stream.
- Las lecturas verificables se resuelven solas y quedan registradas: el track record nace como subproducto.
- Riesgo: lecturas obvias o erróneas. Se mitiga con golden tests sobre carreras reales.
