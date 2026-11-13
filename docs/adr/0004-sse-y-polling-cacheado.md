# 0004. SSE en local y polling cacheado en la nube

- Estado: Aceptado
- Fecha: 2026-11-09

## Contexto

Las actualizaciones van en un solo sentido, del servidor al cliente. El producto prioriza bajo consumo de datos en mobile y costo cercano a cero en la nube.

## Decisión

- En local, la API entrega estado y lecturas por Server-Sent Events.
- En la nube, el nodo propio publica un JSON compacto cada 2 a 5 segundos en almacenamiento de objetos; la CDN lo sirve con TTL corto y los clientes hacen polling con ETag.

## Alternativas descartadas

- WebSocket: la bidireccionalidad no se usa; en AWS, API Gateway WebSocket cobra por mensaje y por minuto de conexión.
- Durable Objects de Cloudflare: opción válida si se elige Cloudflare; se revisa en el ADR 0010.

## Consecuencias

- Mil usuarios generan una consulta al origen por TTL y por ubicación de borde.
- Consumo estimado por usuario: unos 4 a 5 MB en una carrera de 2 horas.
- La latencia sube a 2 a 5 segundos más el TTL. Es aceptable: el timing ya va adelantado respecto de la TV.
- La degradación es simple: si el archivo no se actualiza, la web lo detecta por la marca de tiempo.
