from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Dict


class MetricsRecorder:
    """Lightweight metrics sink safe for unit tests and Redis-backed runtime."""

    def __init__(self, redis_client=None, prefix: str | None = None):
        self.redis = redis_client
        self.prefix = prefix or os.getenv("METRICS_PREFIX", "audit:metrics")
        self._counters: Dict[str, int] = defaultdict(int)
        self._timers: Dict[str, list[float]] = defaultdict(list)

    def inc(self, name: str, value: int = 1) -> None:
        key = f"{self.prefix}:counter:{name}"
        self._counters[key] += value
        if self.redis is not None:
            self.redis.hincrby(key, "value", value)

    def observe(self, name: str, duration_s: float) -> None:
        key = f"{self.prefix}:timer:{name}"
        self._timers[key].append(duration_s)
        if self.redis is not None:
            self.redis.hset(key, mapping={"last": duration_s})

    def timed(self, name: str):
        start = time.time()

        def _finish():
            self.observe(name, time.time() - start)

        return _finish

    def snapshot(self) -> Dict[str, float]:
        data: Dict[str, float] = {}
        for key, value in self._counters.items():
            data[key] = value
        for key, samples in self._timers.items():
            if samples:
                data[key] = samples[-1]
        return data
