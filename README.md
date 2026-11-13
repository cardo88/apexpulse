# ApexPulse

Lectura de carrera de Fórmula 1 en español: convierte el timing en conclusiones con evidencia (ventana de undercut, parada barata bajo Safety Car, degradación, batallas) y genera un análisis post-carrera de una página.

> Proyecto personal, no oficial y sin fines comerciales. No está afiliado a Formula 1 ni a la FIA. Ver [DISCLAIMER.md](DISCLAIMER.md).

## Estado

En construcción. Hito actual: H1, primera lectura por consola. Detalle en [docs/roadmap.md](docs/roadmap.md).

## Cómo funciona

1. Descarga sesiones históricas desde OpenF1 y desde el archivo estático de F1 Live Timing.
2. Normaliza todo a un modelo canónico de eventos, independiente de la fuente.
3. Reproduce la sesión con un reloj controlable y aplica reglas determinísticas que producen lecturas en español.
4. Publica una vista "En carrera" y un post-carrera estático.

Ejemplo de lectura (formato objetivo):

```text
Vuelta 34 | Ventana de undercut: PIA puede salir delante de NOR
Gap 19,8 s; pérdida estimada en boxes 21,4 s; neumático nuevo vale 1,1 s por vuelta.
```

Arquitectura completa en [docs/arquitectura.md](docs/arquitectura.md).

## Arranque rápido

Disponible al cerrar H1. Comandos previstos:

```bash
make setup
make fetch SESSION=2026-sao-paulo-r
make replay SESSION=2026-sao-paulo-r SPEED=30
```

## Documentación

Índice en [docs/README.md](docs/README.md). Las decisiones de arquitectura están en [docs/adr/](docs/adr/README.md).

## Licencia

Código bajo licencia MIT ([LICENSE](LICENSE)). La licencia cubre solo el código de este repositorio; los datos y las marcas de terceros mantienen sus propios términos.
