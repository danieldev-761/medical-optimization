"""Preprocesamiento: filtrado de filas sin valor, limpieza semántica y deduplicación.

Solo la columna mensaje_texto se somete a limpieza; el resto se preserva.
La limpieza es conservadora: elimina ruido/cortesías sin tocar intención,
especialidad, fechas ni preferencias horarias.
"""

import re
from collections.abc import Iterable

import pandas as pd

# Frases accesorias / cortesías sin valor operacional (minúsculas, sin acentos normalizados)
ACCESSORY_PHRASES = re.compile(
    r"\b(por favor|porfavor|muchas gracias|gracias|buenos dias|buenas tardes|buenas noches"
    r"|hola|buen dia|muy amable|saludos|cordialmente|atentamente|urgente|con gusto"
    r"|para su atencion|le agradezco|agradezco|solicito de manera respetuosa|adjunto)\b",
    re.IGNORECASE,
)

# Marca de fin de mensaje: corta en el primer conector que típicamente abre un posdata
# no operativo. Conserva el texto antes (donde vive la intención).
TRAIL_CUTTERS = re.compile(
    r"\s+(att\.|atte\.|saludos a|quedo a su disposicion|muchas gracias de antemano)\b",
    re.IGNORECASE,
)

ACCENT_MAP = str.maketrans(
    "áéíóúüñÁÉÍÓÚÜÑ",
    "aeiouunAEIOUUN",
)


def normalize_ascii(text: str) -> str:
    return text.translate(ACCENT_MAP)


def clean_message(text: str) -> str:
    """Limpieza semántica conservadora de mensaje_texto."""
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text).strip()
    # Tomar la primera oración donde reside la intención operacional de la cita médica
    text = text.split(".")[0].strip()
    text = TRAIL_CUTTERS.split(text)[0]
    text = ACCESSORY_PHRASES.sub("", text)
    text = re.sub(r"[^\w\s.,:;¿?¡!áéíóúüñÁÉÍÓÚÜÑ/()-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" .,;:¿?¡!")


def filter_usable(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Descarta filas vacías/nulas/sin valor semántico. Devuelve (válidas, descartadas)."""
    messages = frame["mensaje_texto"].fillna("").astype(str).str.strip()
    usable = messages.map(lambda m: _has_semantic_value(m))
    valid = frame[usable].copy()
    discarded = frame[~usable].copy()
    return valid, discarded


def _has_semantic_value(message: str) -> bool:
    """Un mensaje tiene valor si tras limpieza conserva términos de intención/datos."""
    if not message or len(message) < 3:
        return False
    cleaned = clean_message(message)
    if not cleaned:
        return False
    if len(cleaned) < 3 and not any(c.isalpha() for c in cleaned):
        return False
    return True


def deduplicate(frame: pd.DataFrame) -> pd.DataFrame:
    """Dedup por mensaje normalizado: conserva la primera ocurrencia por texto limpio."""
    frame = frame.copy()
    frame["_clean_key"] = frame["mensaje_texto"].fillna("").astype(str).map(clean_message)
    frame["_clean_key"] = frame["_clean_key"].map(normalize_ascii).str.lower()
    frame = frame.drop_duplicates(subset="_clean_key", keep="first")
    return frame.drop(columns=["_clean_key"])


def preprocess(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Ejecuta la fase completa de preprocesamiento.

    Devuelve (DataFrame limpio y deduplicado, métricas de reducción de volumen).
    """
    n_before = len(frame)
    frame["mensaje_limpio"] = frame["mensaje_texto"].fillna("").astype(str).map(clean_message)
    valid, discarded = filter_usable(frame)
    before_dedup = len(valid)
    valid = deduplicate(valid)
    n_after = len(valid)
    stats = {
        "filas_leidas": n_before,
        "filas_descartadas_vacio": len(discarded),
        "duplicados_eliminados": before_dedup - n_after,
        "filas_validas": n_after,
    }
    return valid, stats


def iter_batches(frame: pd.DataFrame, batch_size: int) -> Iterable[pd.DataFrame]:
    """Divide un DataFrame en batches de tamaño fijo."""
    for start in range(0, len(frame), batch_size):
        yield frame.iloc[start : start + batch_size]
