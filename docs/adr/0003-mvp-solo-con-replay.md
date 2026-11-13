# 0003. El MVP funciona solo con replay

- Estado: Aceptado
- Fecha: 2026-11-09

## Contexto

El vivo tiene tres obstáculos: OpenF1 cobra el acceso en tiempo real (tier Sponsor, EUR 9,90 por mes), el SignalR de F1 sin autenticación entrega solo los tópicos públicos y F1 bloquea IPs de cloud. Además, entre diciembre de 2026 y marzo de 2027 no hay carreras.

## Decisión

El MVP trabaja exclusivamente con sesiones históricas reproducidas con un reloj controlable. El vivo se incorpora en H7 reutilizando el adaptador del archivo estático.

## Alternativas descartadas

- Vivo desde el primer hito: bloquea el desarrollo a los fines de semana de carrera y agrega costo y riesgo antes de validar el producto.

## Consecuencias

- Se puede desarrollar y probar cualquier día.
- Riesgo: sorpresas del vivo descubiertas tarde. Se mitiga grabando las últimas carreras de 2026 para conocer qué tópicos llegan sin autenticación.
