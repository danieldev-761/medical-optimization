"""Preprocesamiento: filtrado de filas sin valor, limpieza semántica y deduplicación.

Solo la columna mensaje_texto se somete a limpieza; el resto se preserva.
La limpieza es conservadora: elimina ruido/cortesías sin tocar intención,
especialidad, fechas ni preferencias horarias.
"""

import math
import re
from concurrent.futures import ProcessPoolExecutor
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
    """Descarta filas vacías/nulas/sin valor semántico. Devuelve (válidas, descartadas).

    Reutiliza mensaje_limpio si ya fue calculado; de lo contrario limpia al vuelo.
    """
    raw = frame["mensaje_texto"].fillna("").astype(str).str.strip()
    if "mensaje_limpio" in frame.columns:
        cleaned = frame["mensaje_limpio"].fillna("").astype(str)
    else:
        cleaned = raw.map(clean_message)
    usable = [_has_semantic_value(m, c) for m, c in zip(raw.tolist(), cleaned.tolist())]
    valid = frame[usable].copy()
    discarded = frame[[not u for u in usable]].copy()
    return valid, discarded


def _has_semantic_value(message: str, cleaned: str) -> bool:
    """Un mensaje tiene valor si tras limpieza conserva términos de intención/datos."""
    if not message or len(message) < 3:
        return False
    if not cleaned:
        return False
    if len(cleaned) < 3 and not any(c.isalpha() for c in cleaned):
        return False
    return True


def deduplicate(frame: pd.DataFrame) -> pd.DataFrame:
    """Dedup por (paciente_id, mensaje normalizado): conserva la primera ocurrencia de cada paciente por texto limpio."""
    frame = frame.copy()
    if "mensaje_limpio" in frame.columns:
        frame["_clean_key"] = frame["mensaje_limpio"].fillna("").astype(str)
    else:
        frame["_clean_key"] = frame["mensaje_texto"].fillna("").astype(str).map(clean_message)
    frame["_clean_key"] = frame["_clean_key"].map(normalize_ascii).str.lower()
    subset = ["paciente_id", "_clean_key"] if "paciente_id" in frame.columns else ["_clean_key"]
    frame = frame.drop_duplicates(subset=subset, keep="first")
    return frame.drop(columns=["_clean_key"])


def _clean_chunk(chunk_texts: list[str]) -> list[str]:
    """Helper global serializable para ProcessPoolExecutor."""
    return [clean_message(t) for t in chunk_texts]


def clean_texts(texts: list[str], max_workers: int = 4) -> list[str]:
    """Limpia una lista de textos en paralelo por CPU."""
    n = len(texts)
    if n > 100 and max_workers > 1:
        chunk_size = math.ceil(n / max_workers)
        chunks = [texts[i : i + chunk_size] for i in range(0, n, chunk_size)]
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results_nested = list(pool.map(_clean_chunk, chunks))
        return [item for sublist in results_nested for item in sublist]
    return _clean_chunk(texts)


def preprocess(frame: pd.DataFrame, max_workers: int = 4, cleaned_texts: list[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Ejecuta la fase de preprocesamiento: filtra, deduplica y fija mensaje_limpio.

    cleaned_texts: si la limpieza ya fue calculada (p. ej. fusionada con la
    extracción), se reutiliza para no ejecutar clean_message dos veces.
    Devuelve (DataFrame limpio y deduplicado, métricas de reducción de volumen).
    """
    n_before = len(frame)
    if cleaned_texts is None:
        cleaned_texts = clean_texts(frame["mensaje_texto"].fillna("").astype(str).tolist(), max_workers)
    frame["mensaje_limpio"] = cleaned_texts
    valid, discarded = filter_usable(frame)
    if valid.empty:
        raise ValueError("Todas las filas fueron descartadas en preprocesamiento")
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
