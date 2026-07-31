"""Orquestador de la pipeline HU-015 por etapas, con timing y caché."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..config import Settings
from . import extract, ingest, preprocess, report, tokens
from .cost import cost_for
from .metrics import Metrics, stage_timer
from .translate import build_translator

log = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    settings: Settings
    output_frame: pd.DataFrame
    aggregates: dict
    preprocess_stats: dict
    metrics: Metrics
    discarded: pd.DataFrame
    translate_engine: str = "none"


def _extract_fields(frame: pd.DataFrame) -> pd.DataFrame:
    """Extracción vectorizada de los 4 campos estructurados."""
    fields = frame["mensaje_texto"].map(extract.extract_fields)
    extracted = pd.DataFrame(fields.tolist(), index=frame.index)
    for col in ("accion", "especialidad", "fecha_solicitada", "preferencia_horario"):
        if col in frame.columns:
            frame[col] = frame[col].fillna("")
    for col in extracted.columns:
        frame[col] = extracted[col].where(extracted[col].astype(bool), frame.get(col, ""))
    return frame


def _count_tokens_column(frame: pd.DataFrame, column: str, batch_size: int) -> pd.DataFrame:
    """Tokeniza una columna por batches, insertando el conteo en la columna de tokens."""
    suffix = {"mensaje_texto": "original", "mensaje_limpio": "limpio", "mensaje_ingles": "ingles"}[column]
    counts: list[int] = []
    for batch in preprocess.iter_batches(frame, batch_size):
        counts.extend(tokens.count_tokens_batch(batch[column].fillna("").astype(str).tolist()))
    frame[f"tokens_{suffix}"] = counts
    return frame


def _translate_with_cache(frame: pd.DataFrame, settings: Settings, translator) -> tuple[pd.DataFrame, str]:
    """Traduce mensaje_limpio (dedup global, caché) con ThreadPoolExecutor I/O."""
    cleaned = frame["mensaje_limpio"].fillna("").astype(str).tolist()
    # Dedup global para no traducir equivalentes repetidos
    unique = list(dict.fromkeys(cleaned))
    cache: dict[str, str] = {}

    def _run_pool(texts: list[str]) -> list[str]:
        chunk = 100
        results: list[str] = [""] * len(texts)
        jobs = [(i, texts[i : i + chunk]) for i in range(0, len(texts), chunk)]
        with ThreadPoolExecutor(max_workers=settings.max_workers_translate) as pool:
            futures = {
                pool.submit(translator.translate, batch_texts): (idx, batch_texts)
                for idx, batch_texts in jobs
            }
            from concurrent.futures import as_completed

            for future in as_completed(futures):
                idx, batch_texts = futures[future]
                res = future.result()
                results[idx : idx + len(batch_texts)] = res.texts
        return results

    translated_unique = _run_pool(unique)
    cache = dict(zip(unique, translated_unique, strict=True))
    frame["mensaje_ingles"] = [cache.get(t, t) for t in cleaned]
    return frame, cache


def run_pipeline(settings: Settings) -> PipelineResult:
    """Ejecuta la pipeline completa y devuelve los artefactos."""
    metrics = Metrics()

    with stage_timer(metrics, "ingesta"):
        raw = ingest.ingest(settings)

    with stage_timer(metrics, "validacion"):
        from .validate import parseable_messages, validate_columns

        validate_columns(raw)
        raw = parseable_messages(raw)
        if raw.empty:
            raise ValueError("No hay filas procesables tras la validación")

    with stage_timer(metrics, "csv_intermedio"):
        ingest.to_csv_intermediate(raw, Path(settings.output_csv))

    with stage_timer(metrics, "preprocesamiento"):
        valid, preprocess_stats = preprocess.preprocess(raw)
        if valid.empty:
            raise ValueError("Todas las filas fueron descartadas en preprocesamiento")

    with stage_timer(metrics, "extraccion"):
        valid = _extract_fields(valid)

    with stage_timer(metrics, "tokens_original"):
        valid = _count_tokens_column(valid, "mensaje_texto", settings.batch_size)
    with stage_timer(metrics, "tokens_limpio"):
        valid = _count_tokens_column(valid, "mensaje_limpio", settings.batch_size)

    translate_engine = "none"
    if settings.optimize_tokens:
        translator = build_translator(settings.translate_engine, settings.model_dir)
        with stage_timer(metrics, "traduccion"):
            valid, _cache = _translate_with_cache(valid, settings, translator)
            translate_engine = translator.engine
        with stage_timer(metrics, "tokens_ingles"):
            valid = _count_tokens_column(valid, "mensaje_ingles", settings.batch_size)
    else:
        valid["tokens_ingles"] = 0
        valid["mensaje_ingles"] = ""

    with stage_timer(metrics, "costeo"):
        valid["costo_estimado_original"] = valid["tokens_original"].map(cost_for)
        valid["costo_estimado_limpio"] = valid["tokens_limpio"].map(cost_for)
        valid["costo_estimado_ingles"] = valid["tokens_ingles"].map(cost_for)

    with stage_timer(metrics, "reporte"):
        output = report.build_output_frame(valid)
        aggregates = report.compute_aggregates(valid)
        aggregates["preprocesamiento"] = preprocess_stats
        aggregates["motores"] = {"traduccion": translate_engine}
        report.write_excel(output, settings.output_excel)
        _write_json(settings.output_json, aggregates)

    if settings.metrics_path:
        _write_json(settings.metrics_path, {"etapas_seg": metrics.to_dict()})

    return PipelineResult(
        settings=settings,
        output_frame=output,
        aggregates=aggregates,
        preprocess_stats=preprocess_stats,
        metrics=metrics,
        discarded=raw.loc[~raw.index.isin(valid.index)],
        translate_engine=translate_engine,
    )


def _write_json(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
