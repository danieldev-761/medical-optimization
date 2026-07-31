"""Configuración central de la pipeline HU-015."""

import os
from dataclasses import dataclass, field
from pathlib import Path

# Columnas obligatorias de entrada
REQUIRED_COLUMNS = ["paciente_id", "mensaje_texto"]

# Columnas opcionales preservadas como trazabilidad
OPTIONAL_COLUMNS = [
    "fecha_solicitada",
    "preferencia_horario",
    "especialidad",
    "accion",
]

# Contrato de salida Excel (orden exacto)
OUTPUT_COLUMNS = [
    "paciente_id",
    "paciente",
    "mensaje_texto",
    "mensaje_limpio",
    "mensaje_ingles",
    "accion",
    "especialidad",
    "fecha_solicitada",
    "preferencia_horario",
    "tokens_original",
    "tokens_limpio",
    "tokens_ingles",
    "costo_estimado_original",
    "costo_estimado_limpio",
    "costo_estimado_ingles",
]

# Tarifa USD por millón de tokens
RATE_USD_PER_MILLION = 2.50

# Proyección hipotética
PROJECTED_MESSAGES_PER_DAY = 15_000
PROJECTION_PERIODS = {
    "diario": 1,
    "mensual": 30,
    "trimestral": 90,
    "anual": 365,
}

# Rendimiento
DEFAULT_BATCH_SIZE = 500
MAX_WORKERS_INGEST = 4
MAX_WORKERS_TRANSLATE = 8
TRANSLATE_TIMEOUT = 30
TRANSLATE_MAX_RETRIES = 2

# Traducción
CTRANSLATE2_MODEL = "en-es"  # ctranslate2 no traduce ES->EN; ver nota en translate.py
CTRANSLATE2_OPUS = "opus-mt-es-en"
LOCAL_TRANSLATE_MODEL_DIR = "models/opus-mt-es-en"


@dataclass
class Settings:
    """Configuración de una corrida de la pipeline."""

    input_path: str
    output_excel: str = "out/resultados.xlsx"
    output_json: str = "out/agregados.json"
    output_csv: str = "out/intermediate.csv"
    optimize_tokens: bool = True
    batch_size: int = DEFAULT_BATCH_SIZE
    translate_engine: str = "auto"  # "ctranslate2" | "deep_translator" | "auto"
    model_dir: str = LOCAL_TRANSLATE_MODEL_DIR
    cache_enabled: bool = True
    redis_enabled: bool = True
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    redis_db: int = 0
    redis_ttl_days: int = 30
    metrics_path: str | None = "out/metrics.json"
    max_workers_ingest: int = MAX_WORKERS_INGEST
    max_workers_translate: int = MAX_WORKERS_TRANSLATE
    translate_timeout: int = TRANSLATE_TIMEOUT
    translate_max_retries: int = TRANSLATE_MAX_RETRIES
    input_path_obj: Path = field(init=False)

    def __post_init__(self) -> None:
        self.input_path_obj = Path(self.input_path)
