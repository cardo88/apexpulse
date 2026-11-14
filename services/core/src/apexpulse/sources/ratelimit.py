"""Límite de tasa por ventanas deslizantes, con estado opcional compartido entre ejecuciones.

Ejemplo para OpenF1: `RateLimiter([(1.0, 3), (60.0, 30)])` admite como máximo 3 requests en
cualquier segundo y 30 en cualquier minuto. Con `state_file`, los instantes de los últimos
requests se guardan en disco: dos `make fetch` seguidos comparten el mismo presupuesto.
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path


class RateLimiter:
    """Bloquea en `acquire()` hasta que un request nuevo respete todas las ventanas."""

    def __init__(
        self,
        windows: Sequence[tuple[float, int]],
        *,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        state_file: Path | None = None,
    ) -> None:
        if not windows or any(periodo <= 0 or limite <= 0 for periodo, limite in windows):
            raise ValueError("cada ventana necesita periodo y límite positivos")
        self._windows = sorted(windows)
        self._max_period = max(periodo for periodo, _ in self._windows)
        self._max_limit = max(limite for _, limite in self._windows)
        self._clock = clock
        self._sleep = sleep
        self._state_file = state_file
        self._stamps: deque[float] = deque(maxlen=self._max_limit)
        self._load()

    def wait_time(self) -> float:
        """Segundos que faltan para poder hacer un request sin violar ninguna ventana."""
        ahora = self._clock()
        espera = 0.0
        for periodo, limite in self._windows:
            if len(self._stamps) >= limite:
                referencia = self._stamps[-limite]
                espera = max(espera, referencia + periodo - ahora)
        return espera

    def acquire(self) -> None:
        """Espera lo necesario y registra el request."""
        while (espera := self.wait_time()) > 0:
            self._sleep(espera)
        self._stamps.append(self._clock())
        self._save()

    def _load(self) -> None:
        if self._state_file is None or not self._state_file.exists():
            return
        try:
            guardados = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # estado corrupto: se descarta, en el peor caso el servidor responde 429
        if not isinstance(guardados, list):
            return
        limite = self._clock() - self._max_period
        recientes = sorted(float(t) for t in guardados if isinstance(t, int | float) and t > limite)
        self._stamps.extend(recientes)

    def _save(self) -> None:
        if self._state_file is None:
            return
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        temporal = self._state_file.with_suffix(".tmp")
        temporal.write_text(json.dumps(list(self._stamps)), encoding="utf-8")
        os.replace(temporal, self._state_file)
