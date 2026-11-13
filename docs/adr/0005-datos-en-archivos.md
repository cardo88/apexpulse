# 0005. Los datos viven en archivos, sin base de datos servidor

- Estado: Aceptado
- Fecha: 2026-11-09

## Contexto

Hay un solo escritor (la ingesta), las lecturas del post-carrera son analíticas y el objetivo de costo es cercano a cero. El mismo layout tiene que funcionar en la compu y en almacenamiento de objetos.

## Decisión

- Crudo en JSONL comprimido con zstd.
- Eventos canónicos en Parquet.
- Consultas con DuckDB embebido.

## Alternativas descartadas

- Postgres o TimescaleDB: un servicio más que operar, respaldar y pagar.
- SQLite: válido, pero menos cómodo para consultas columnares sobre Parquet en S3.

## Consecuencias

- Cero servidores de base de datos, en local y en la nube.
- Una migración de esquema equivale a renormalizar desde el crudo.
- No hay escrituras concurrentes; no se necesitan.
