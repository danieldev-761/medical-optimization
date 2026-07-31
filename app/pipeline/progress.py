"""Reporter de progreso de la pipeline para streaming en tiempo real.

Emite eventos (etapa, progreso 0-1) con pesos por etapa, de modo que el
frontend pueda mostrar una barra de carga que avanza de forma realista.

Uso por parte de la pipeline:
    reporter.stage("ingesta")   # emite inicio de etapa
    ... trabajo ...
    reporter.end("ingesta")     # acumula el peso completado

Para etapas pesadas con sub-progreso (traducción):
    reporter.stage("traduccion")
    ... on_batch: reporter.sub(fraction) ...
    reporter.end("traduccion")
"""

from __future__ import annotations

from collections.abc import Callable

ProgressListener = Callable[[str, float], None]

STAGE_WEIGHTS: dict[str, float] = {
    "ingesta": 0.06,
    "validacion": 0.02,
    "csv_intermedio": 0.02,
    "preprocesamiento": 0.05,
    "extraccion": 0.06,
    "tokens_original": 0.07,
    "tokens_limpio": 0.05,
    "traduccion": 0.5,
    "tokens_ingles": 0.05,
    "costeo": 0.02,
    "reporte": 0.10,
}


class ProgressReporter:
    """Acumula el avance ponderado por etapas y notifica al listener."""

    def __init__(self, listener: ProgressListener, optimize_tokens: bool):
        self._listener = listener
        self._active = [
            name
            for name in STAGE_WEIGHTS
            if optimize_tokens or name not in ("traduccion", "tokens_ingles")
        ]
        self._total = sum(STAGE_WEIGHTS[name] for name in self._active)
        self._cumulative = 0.0
        self._stage_base = 0.0
        self._stage_weight = 0.0
        self._stage_name = ""

    def stage(self, name: str) -> None:
        """Notifica el inicio de una etapa y fija su base de avance."""
        self._emit(name, self._fraction(self._cumulative))
        self._stage_base = self._cumulative
        self._stage_weight = STAGE_WEIGHTS.get(name, 0.0)
        self._stage_name = name

    def sub(self, fraction: float) -> None:
        """Progreso parcial dentro de la etapa actual (0-1)."""
        pct = self._stage_base + self._stage_weight * fraction
        self._emit(self._stage_name, self._fraction(pct))

    def end(self, name: str) -> None:
        """Acumula el peso de la etapa ya completada."""
        self._cumulative += STAGE_WEIGHTS.get(name, 0.0)

    def done(self) -> None:
        self._emit("reporte", 1.0)

    def _fraction(self, value: float) -> float:
        return round(min(max(value / self._total if self._total else 0.0, 0.0), 1.0), 4)

    def _emit(self, name: str, fraction: float) -> None:
        if self._listener:
            self._listener(name, fraction)
