"""Capa de ingesta: archivo .xlsx único o carpeta, consolidación y conversión a CSV."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from ..config import Settings


def _discover_inputs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        if input_path.suffix.lower() != ".xlsx":
            raise ValueError(f"El archivo de entrada debe ser .xlsx: {input_path}")
        return [input_path]
    if input_path.is_dir():
        files = sorted(input_path.rglob("*.xlsx"))
        if not files:
            raise ValueError(f"No se encontraron archivos .xlsx en {input_path}")
        return files
    raise ValueError(f"La ruta de entrada no existe: {input_path}")


def _load_sheet(path: Path) -> pd.DataFrame:
    """Carga una hoja .xlsx a DataFrame sin costo de celdas vacías residuales."""
    return pd.read_excel(path, engine="openpyxl", dtype=str)


def read_excel_to_dataframes(files: list[Path], max_workers: int = 4) -> list[pd.DataFrame]:
    """Lectura concurrente de archivos (I/O-bound): un worker por archivo."""
    if len(files) == 1:
        return [_load_sheet(files[0])]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(_load_sheet, files))


def consolidate(frames: list[pd.DataFrame], source_files: list[Path]) -> pd.DataFrame:
    """Consolida DataFrames preservando trazabilidad por archivo origen."""
    result: list[pd.DataFrame] = []
    for frame, path in zip(frames, source_files, strict=True):
        frame = frame.copy()
        frame.insert(0, "archivo_origen", str(path))
        result.append(frame)
    return pd.concat(result, ignore_index=True)


def ingest(settings: Settings) -> pd.DataFrame:
    """Ingesta completa: descubre archivos, carga y consolida en un único DataFrame."""
    files = _discover_inputs(settings.input_path_obj)
    frames = read_excel_to_dataframes(files, max_workers=settings.max_workers_ingest)
    return consolidate(frames, files)
