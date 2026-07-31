"""Validación de columnas obligatorias antes de cualquier etapa semántica."""

import pandas as pd

from ..config import REQUIRED_COLUMNS


class ColumnValidationError(ValueError):
    """Se lanza cuando faltan columnas obligatorias o el mensaje no es parseable."""


def validate_columns(frame: pd.DataFrame) -> None:
    """Valida presencia de columnas obligatorias, normalizando nombres esperados."""
    frame.columns = [str(c).strip().lower() for c in frame.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ColumnValidationError(
            f"Faltan columnas obligatorias: {missing}. "
            f"Columnas encontradas: {list(frame.columns)}"
        )


def parseable_messages(frame: pd.DataFrame) -> pd.DataFrame:
    """Descarta filas donde mensaje_texto no sea parseable (nulo o no-string usable)."""
    messages = frame["mensaje_texto"].astype(str).fillna("")
    return frame.assign(mensaje_texto=messages)
