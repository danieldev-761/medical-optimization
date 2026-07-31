"""Instrumentación de tiempos por etapa para profiling."""

import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class Metrics:
    """Acumula duraciones por etapa de la pipeline."""

    stages: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, float]:
        return dict(self.stages)


@contextmanager
def stage_timer(metrics: Metrics, name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        metrics.stages[name] = metrics.stages.get(name, 0.0) + (time.perf_counter() - start)


def timed(func: Callable) -> Callable:
    """Decorador de utilidad; la medición real se hace con stage_timer en la pipeline."""

    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper
