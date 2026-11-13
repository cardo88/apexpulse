# 0002. Un modelo canónico de eventos separa fuentes y motor

- Estado: Aceptado
- Fecha: 2026-11-09

## Contexto

El feed de F1 se conoce por ingeniería inversa y cambió entre 2025 y 2026: nuevo endpoint `/signalrcore` y tópicos que pasaron a requerir F1 TV. El proyecto combina fuentes con formatos distintos (OpenF1, archivo estático de Live Timing, Jolpica-F1) y en H7 suma el vivo.

## Decisión

Cada fuente tiene un adaptador que guarda el crudo, valida el esquema con Pydantic en modo estricto y emite eventos canónicos v1. Ninguna parte del código fuera de `sources/` conoce el formato de una fuente. El esquema canónico se versiona.

## Alternativas descartadas

- Reglas que leen OpenF1 directamente: acoplan la lógica de producto a una fuente que puede cambiar o encarecerse.
- Usar los objetos de FastF1 como modelo: depende de pandas, es pesado y está atado al archivo estático.

## Consecuencias

- Un cambio de esquema afecta un solo adaptador y se diagnostica con el crudo guardado.
- El vivo de H7 reutiliza el parser del archivo estático, que tiene el mismo formato.
- Costo: una capa más y la disciplina de versionar el esquema. Se cubre con tests de contrato.
