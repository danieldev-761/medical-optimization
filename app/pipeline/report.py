"""Presentación: Excel final de una sola hoja y agregados para dashboard."""

from pathlib import Path

import pandas as pd

from ..config import OUTPUT_COLUMNS, PROJECTED_MESSAGES_PER_DAY
from . import cost as cost_mod


def build_output_frame(processed: pd.DataFrame) -> pd.DataFrame:
    """Ensambla el DataFrame con el contrato exacto de columnas del Excel."""
    out = pd.DataFrame()
    for col in OUTPUT_COLUMNS:
        if col in processed.columns:
            out[col] = processed[col]
        else:
            out[col] = None
    return out


def write_excel(frame: pd.DataFrame, path: str | Path) -> None:
    """Escribe el Excel final con una sola hoja usando xlsxwriter ultrarrápido."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        frame.to_excel(path, index=False, sheet_name="Resultados", engine="xlsxwriter")
    except Exception:  # noqa: BLE001
        frame.to_excel(path, index=False, sheet_name="Resultados", engine="openpyxl")


def compute_aggregates(processed: pd.DataFrame) -> dict:
    """Agregados reales del lote procesado y proyección hipotética."""
    total_original = int(processed["tokens_original"].fillna(0).sum())
    total_limpio = int(processed["tokens_limpio"].fillna(0).sum())
    total_ingles = int(processed["tokens_ingles"].fillna(0).sum())

    cost_original = cost_mod.cost_for(total_original)
    cost_limpio = cost_mod.cost_for(total_limpio)
    cost_ingles = cost_mod.cost_for(total_ingles)

    saving_limpio = cost_original - cost_limpio
    saving_ingles = cost_original - cost_ingles
    saving_limpio_pct = (saving_limpio / cost_original * 100) if cost_original else 0.0
    saving_ingles_pct = (saving_ingles / cost_original * 100) if cost_original else 0.0

    n = len(processed)
    avg_tokens = {
        "original": (total_original / n) if n else 0.0,
        "limpio": (total_limpio / n) if n else 0.0,
        "ingles": (total_ingles / n) if n else 0.0,
    }

    aggregates = {
        "n_procesadas": n,
        "totales": {
            "tokens_original": total_original,
            "tokens_limpio": total_limpio,
            "tokens_ingles": total_ingles,
            "costo_original": cost_original,
            "costo_limpio": cost_limpio,
            "costo_ingles": cost_ingles,
        },
        "ahorro": {
            "limpio_absoluto": saving_limpio,
            "limpio_pct": saving_limpio_pct,
            "ingles_absoluto": saving_ingles,
            "ingles_pct": saving_ingles_pct,
        },
        "promedio_tokens_por_mensaje": avg_tokens,
        "distribucion_acciones": (
            processed["accion"].fillna("(sin accion)").value_counts().to_dict() if "accion" in processed else {}
        ),
        "distribucion_especialidades": (
            processed["especialidad"].fillna("(sin especialidad)").value_counts().to_dict()
            if "especialidad" in processed
            else {}
        ),
    }

    if processed["tokens_ingles"].notna().any():
        aggregates["proyeccion"] = cost_mod.build_projection(avg_tokens)
    else:
        # Sin modo optimizar_tokens: proyección sobre original y limpio únicamente
        aggregates["proyeccion"] = cost_mod.build_projection(
            {k: v for k, v in avg_tokens.items() if k != "ingles"}
        )
    aggregates["proyeccion"]["_meta"] = {
        "mensajes_por_dia": PROJECTED_MESSAGES_PER_DAY,
        "tarifa_usd_por_millon": cost_mod.RATE_USD_PER_MILLION,
    }
    return aggregates
