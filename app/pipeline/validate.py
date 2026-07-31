"""Validación de columnas obligatorias antes de cualquier etapa semántica."""

import pandas as pd

from ..config import REQUIRED_COLUMNS

# Alias aceptados de columnas obligatorias según el formato de origen
COLUMN_ALIASES = {
    "id_paciente": "paciente_id",
    "mensaje": "mensaje_texto",
    "especialidad_medica": "especialidad",
}


class ColumnValidationError(ValueError):
    """Se lanza cuando faltan columnas obligatorias o el mensaje no es parseable."""


def validate_columns(frame: pd.DataFrame) -> None:
    """Valida presencia de columnas obligatorias, normalizando nombres esperados."""
    frame.columns = [str(c).strip().lower() for c in frame.columns]
    frame.rename(columns={alias: canonical for alias, canonical in COLUMN_ALIASES.items() if alias in frame.columns}, inplace=True)
    # Guardia contra duplicados tras normalización de alias (formatos mixtos)
    if len(frame.columns) != frame.columns.nunique():
        frame = frame.loc[:, ~frame.columns.duplicated(keep="first")]
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
