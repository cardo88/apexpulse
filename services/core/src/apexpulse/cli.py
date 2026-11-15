"""Línea de comandos de apexpulse; la invocan los targets de make.

Uso:
- `python -m apexpulse fetch 2026-sao-paulo-r [--force] [--data-dir DIR]`
- `python -m apexpulse normalize 2026-sao-paulo-r [--data-dir DIR]`
- `python -m apexpulse replay 2026-sao-paulo-r [--speed N | --no-wait] [--from-lap N] [--verbose]`

El directorio de datos es, en orden: `--data-dir`, `APEXPULSE_DATA_DIR` o `./data`.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from apexpulse.model import TrackStatusChanged, write_events
from apexpulse.replay import ConsolePrinter, Replay, ReplayError, SystemClock
from apexpulse.session_id import SessionId, SessionIdError
from apexpulse.sources.base import FetchReport, SourceError
from apexpulse.sources.openf1 import RATE_LIMITS, OpenF1Adapter
from apexpulse.sources.ratelimit import RateLimiter


def _data_dir(valor: str | None) -> Path:
    return Path(valor or os.environ.get("APEXPULSE_DATA_DIR") or "data").resolve()


def _imprimir(report: FetchReport) -> None:
    origen = "caché local, 0 requests" if report.from_cache else f"{report.requests} requests"
    print(f"{report.session} ({report.source}, session_key {report.source_session_key}): {origen}")
    for endpoint, filas in report.rows.items():
        print(f"  {endpoint:<13} {filas:>7} registros")
    for aviso in report.warnings:
        print(f"AVISO: {aviso}", file=sys.stderr)
    print(f"Crudo en {report.dest}")


def _fetch(args: argparse.Namespace) -> int:
    session = SessionId.parse(args.session)
    data = _data_dir(args.data_dir)
    limiter = RateLimiter(RATE_LIMITS, state_file=data / "state" / "openf1-ratelimit.json")
    adapter = OpenF1Adapter(limiter=limiter)
    _imprimir(adapter.fetch(session, data / "raw", force=args.force))
    return 0


def canonical_path(data: Path, session: SessionId) -> Path:
    """Ruta del Parquet canónico de una sesión: data/canonical/<sesion>.parquet."""
    return data / "canonical" / f"{session}.parquet"


def _normalize(args: argparse.Namespace) -> int:
    session = SessionId.parse(args.session)
    data = _data_dir(args.data_dir)
    resultado = OpenF1Adapter().normalize(session, data / "raw")
    destino = canonical_path(data, session)
    total = write_events(destino, resultado.meta, resultado.events)
    print(f"{session} (openf1 a canónico v{resultado.meta.schema_version}): {total} eventos")
    for tipo, n in sorted(Counter(e.kind for e in resultado.events).items()):
        print(f"  {tipo:<13} {n:>7}")
    estados = sorted(
        (e for e in resultado.events if isinstance(e, TrackStatusChanged)), key=lambda e: e.t
    )
    if estados:
        print("Estado de pista:")
        for e in estados:
            vuelta = "" if e.lap is None else f"vuelta {e.lap:>2}  "
            print(f"  {e.t:%H:%M:%S}  {vuelta}{e.status.value:<10} {e.cause}")
    for aviso in resultado.warnings:
        print(f"AVISO: {aviso}", file=sys.stderr)
    print(f"Canónico en {destino}")
    return 0


def _replay(args: argparse.Namespace) -> int:
    session = SessionId.parse(args.session)
    origen = canonical_path(_data_dir(args.data_dir), session)
    if not origen.exists():
        raise ReplayError(f"no existe {origen}: correr make normalize SESSION={session}")
    speed = None if args.no_wait else args.speed
    replay = Replay.from_parquet(origen, SystemClock(), speed=speed)
    if args.from_lap is not None:
        replay.seek_lap(args.from_lap)
    ritmo = "sin espera" if speed is None else f"x{speed:g}"
    meta = replay.meta
    print(f"{meta.session} · {meta.circuit} · {meta.source} · {ritmo} · hora UTC")
    printer = ConsolePrinter(replay.state, verbose=args.verbose)
    emitidos = 0
    try:
        for lote in replay.run():
            emitidos += len(lote)
            for linea in printer.lines(lote):
                print(linea, flush=True)
    except KeyboardInterrupt:
        print(f"Replay interrumpido en {replay.position:%H:%M:%S}", file=sys.stderr)
        return 130
    except BrokenPipeError:
        # La salida se cortó (por ejemplo, `| head`): no es un error del replay.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    print(f"Fin del replay: {emitidos} eventos, vuelta {replay.state.lap}")
    return 0


def _velocidad(valor: str) -> float:
    try:
        speed = float(valor)
    except ValueError:
        speed = 0.0
    if not speed > 0:
        raise argparse.ArgumentTypeError(f"tiene que ser un número mayor que 0: {valor!r}")
    return speed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="apexpulse", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)

    fetch = sub.add_parser("fetch", help="descarga y cachea una sesión desde OpenF1")
    fetch.add_argument(
        "session", help="identificador <año>-<circuito>-<tipo>, por ejemplo 2026-sao-paulo-r"
    )
    fetch.add_argument("--force", action="store_true", help="ignora la caché y vuelve a bajar")
    fetch.add_argument("--data-dir", help="directorio de datos (por defecto ./data)")
    fetch.set_defaults(func=_fetch)

    normalize = sub.add_parser(
        "normalize", help="convierte el crudo descargado en eventos canónicos v1 (Parquet)"
    )
    normalize.add_argument("session", help="identificador <año>-<circuito>-<tipo>")
    normalize.add_argument("--data-dir", help="directorio de datos (por defecto ./data)")
    normalize.set_defaults(func=_normalize)

    replay = sub.add_parser("replay", help="reproduce una sesión canónica por consola")
    replay.add_argument("session", help="identificador <año>-<circuito>-<tipo>")
    ritmo = replay.add_mutually_exclusive_group()
    ritmo.add_argument(
        "--speed", type=_velocidad, default=1.0, help="multiplicador de velocidad (por defecto 1)"
    )
    ritmo.add_argument("--no-wait", action="store_true", help="reproduce sin esperar")
    replay.add_argument("--from-lap", type=int, help="empieza en esta vuelta del líder")
    replay.add_argument("--verbose", action="store_true", help="imprime cada evento")
    replay.add_argument("--data-dir", help="directorio de datos (por defecto ./data)")
    replay.set_defaults(func=_replay)

    args = parser.parse_args(argv)
    try:
        resultado: int = args.func(args)
    except (SessionIdError, SourceError, ReplayError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return resultado


if __name__ == "__main__":
    raise SystemExit(main())
