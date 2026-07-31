"""Costeo con tarifa de 2.50 USD por millón de tokens.

costo_estimado = (tokens / 1_000_000) * 2.50
"""

from ..config import PROJECTED_MESSAGES_PER_DAY, PROJECTION_PERIODS, RATE_USD_PER_MILLION


def cost_for(tokens: int, rate: float = RATE_USD_PER_MILLION) -> float:
    return round((tokens / 1_000_000) * rate, 6)


def project_cost(avg_tokens_per_message: float, period_days: int, messages_per_day: int = PROJECTED_MESSAGES_PER_DAY) -> dict:
    """Proyección hipotética de costo para un volumen y periodo."""
    messages = messages_per_day * period_days
    tokens_total = avg_tokens_per_message * messages
    return {
        "mensajes": messages,
        "tokens": round(tokens_total),
        "costo": round(cost_for(tokens_total), 6),
    }


def build_projection(avg_tokens_by_variant: dict[str, float]) -> dict[str, dict[str, dict]]:
    """Proyección diaria, mensual, trimestral y anual por variante.

    avg_tokens_by_variant: {"original": x, "limpio": y, "ingles": z}
    """
    projection: dict[str, dict[str, dict]] = {}
    for variant, avg_tokens in avg_tokens_by_variant.items():
        projection[variant] = {
            period: project_cost(avg_tokens, days) for period, days in PROJECTION_PERIODS.items()
        }
    return projection
