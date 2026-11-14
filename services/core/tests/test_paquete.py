"""Verifica que el paquete se instala e importa desde el entorno de uv."""

import apexpulse


def test_version_definida() -> None:
    assert apexpulse.__version__ == "0.0.0"
