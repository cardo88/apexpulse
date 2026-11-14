# Roadmap

Hitos de ApexPulse y su estado. Cada hito cierra con una versión etiquetada y un criterio verificable. Los cambios de alcance pasan por un ADR.

## Alcance del MVP

### Entra

- Ingesta histórica desde OpenF1 con caché local y límite de 3 req/s.
- Adaptador del archivo estático de Live Timing (mismo formato que el vivo).
- Modelo canónico de eventos v1, independiente de la fuente y versionado.
- Motor de lecturas con 5 reglas determinísticas:
  1. Ventana de undercut u overcut.
  2. Parada barata bajo Safety Car o VSC.
  3. Degradación del stint.
  4. Batalla sostenida: gap menor a 1 s durante 3 vueltas o más.
  5. Cambio de condiciones: lluvia o temperatura de pista.
- Replay con reloj controlable (x1 a x60, salto a vuelta) servido por SSE.
- Web "En carrera": lecturas, tabla compacta y race trace; mobile primero; 150 KB como máximo en la carga inicial; modo noche.
- Post-carrera de una página, estático, con imagen para compartir.

### Queda afuera

- Ingesta en vivo (H7).
- Telemetría de auto, mapa de pista con posiciones y radio de equipo.
- Autenticación con F1 TV en cualquier componente.
- Predicciones probabilísticas, ML y track record público (backlog).
- Overlays para OBS, fantasy, cuentas de usuario y notificaciones push.
- Texto generado por LLM en tiempo real.
- Otros idiomas y temporadas anteriores a 2023.

### Criterio de MVP terminado

- Replay de 3 carreras de 2026 con al menos una lectura correcta de cada regla, verificada a mano.
- Post-carrera generado para esas 3 carreras.
- `docker compose up` funciona en menos de 5 minutos desde un clon limpio.
- CI en verde y documentación al día.

## Hitos

| Hito | Entregable | Criterio de cierre | Estado |
|------|------------|--------------------|--------|
| H1. Primera lectura | v0.1.0: docs y skills base, ingesta OpenF1, modelo canónico, replay por consola, 2 reglas | `make replay SESSION=2026-sao-paulo-r SPEED=30` imprime lecturas en español con vuelta y evidencia; CI en verde | En curso |
| H2. Motor v1 | v0.2.0: 5 reglas, adaptador del archivo estático, golden tests sobre 3 carreras | Cada regla con un caso real verificado y documentado en docs/lecturas.md | Pendiente |
| H3. Vista "En carrera" | v0.3.0: API con SSE, web mobile primero, identidad visual v1 | 150 KB o menos en la carga inicial; replay fluido a x30 en un teléfono de gama media | Pendiente |
| H4. Post-carrera | v0.4.0: página estática por sesión con imagen para compartir | 3 post-carreras generados con un comando y revisados | Pendiente |
| H5. Puesta a punto | v0.5.0: degradación controlada, logs estructurados, runbook, accesibilidad, prueba con red 3G | MVP terminado según el criterio anterior | Pendiente |
| H6. Nube estática | v0.6.0: infraestructura como código, almacenamiento y CDN, CI/CD con OIDC, post-carrera automático | Sitio público con disclaimer y budget con alarma activo | Pendiente |
| H7. Vivo | v0.7.0: nodo propio, publicación por polling, demora configurable contra spoilers | Probado en una sesión real | Pendiente |
| Backlog | Track record de lecturas verificables, overlays para OBS, resumen asistido, fantasy | Se prioriza con ADR | |

## H1: tareas

| Tarea | Descripción | Estado |
|-------|-------------|--------|
| 1 | Estructura, LICENSE, DISCLAIMER, README, AGENTS.md, CLAUDE.md, CHANGELOG, skills base | Hecha |
| 2 | ADR 0001 a 0008 | Hecha |
| 3 | CI en GitHub Actions, check-docs, check-skills, make mapa, hook Stop | Hecha |
| 4 | Adaptador OpenF1 con caché y límite de tasa; `make fetch` | Hecha |
| 5 | Modelo canónico v1 y normalizador; docs/modelo-de-eventos.md | Pendiente |
| 6 | Reloj de replay y `make replay` | Pendiente |
| 7 | Reglas "parada barata bajo SC/VSC" y "ventana de undercut" | Pendiente |
| 8 | Golden test; docs/setup-local.md y docs/lecturas.md | Pendiente |
