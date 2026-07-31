"""Orquestador de la pipeline HU-015 por etapas, con timing y caché."""

import json
import logging
from collections.abc import Callable
import math
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from ..config import Settings
from . import extract, ingest, preprocess, report, tokens
from .cost import cost_for
from .metrics import Metrics, stage_timer
from .progress import ProgressListener, ProgressReporter
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


def _extract_chunk(chunk_texts: list[str]) -> list[dict]:
    """Helper global serializable para ProcessPoolExecutor."""
    return [extract.extract_fields(t) for t in chunk_texts]


def _extract_fields(frame: pd.DataFrame, max_workers: int = 4) -> pd.DataFrame:
    """Extracción paralelizada por CPU de los 4 campos estructurados."""
    texts = frame["mensaje_texto"].tolist()
    n = len(texts)

    if n > 100 and max_workers > 1:
        chunk_size = math.ceil(n / max_workers)
        chunks = [texts[i : i + chunk_size] for i in range(0, n, chunk_size)]
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results_nested = list(pool.map(_extract_chunk, chunks))
        extracted_dicts = [item for sublist in results_nested for item in sublist]
    else:
        extracted_dicts = _extract_chunk(texts)

    extracted = pd.DataFrame(extracted_dicts, index=frame.index)
    for col in ("accion", "especialidad", "fecha_solicitada", "preferencia_horario"):
        if col in frame.columns:
            frame[col] = frame[col].fillna("")
    for col in extracted.columns:
        frame[col] = extracted[col].where(extracted[col].astype(bool), frame.get(col, ""))
    return frame


def _count_tokens_column(frame: pd.DataFrame, column: str, batch_size: int) -> pd.DataFrame:
    """Tokeniza una columna directamente en C/Rust en una sola llamada masiva."""
    suffix = {"mensaje_texto": "original", "mensaje_limpio": "limpio", "mensaje_ingles": "ingles"}[column]
    texts = frame[column].fillna("").astype(str).tolist()
    frame[f"tokens_{suffix}"] = tokens.count_tokens_batch(texts)
    return frame


from .cache import TranslationCache


def _translate_with_cache(
    frame: pd.DataFrame, settings: Settings, translator, on_batch: Callable | None = None
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Traduce mensaje_limpio (dedup por oración semántica + caché Redis/memoria)."""
    cleaned = frame["mensaje_limpio"].fillna("").astype(str).tolist()
    unique = list(dict.fromkeys(cleaned))

    cache_manager = TranslationCache(settings)
    cached_map = cache_manager.get_many(unique)

    missing = [t for t in unique if t not in cached_map]

    def _run_pool(texts: list[str]) -> list[str]:
        if not texts:
            return []
        if translator.engine == "ctranslate2":
            return translator.translate(texts).texts
        chunk = 1000
        results: list[str] = [""] * len(texts)
        jobs = [(i, texts[i : i + chunk]) for i in range(0, len(texts), chunk)]
        total_jobs = len(jobs)
        done_jobs = 0
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
                done_jobs += 1
                if on_batch:
                    on_batch(done_jobs, total_jobs)
        return results

    if missing:
        translated_missing = _run_pool(missing)
        new_translations = dict(zip(missing, translated_missing, strict=True))
        cache_manager.set_many(new_translations)
        cached_map.update(new_translations)

    frame["mensaje_ingles"] = [cached_map.get(t, t) for t in cleaned]
    return frame, cached_map


def run_pipeline(settings: Settings, progress: ProgressListener | None = None) -> PipelineResult:
    """Ejecuta la pipeline completa y devuelve los artefactos."""
    metrics = Metrics()
    reporter = ProgressReporter(progress, settings.optimize_tokens)

    reporter.stage("ingesta")
    with stage_timer(metrics, "ingesta"):
        raw = ingest.ingest(settings)
    reporter.end("ingesta")

    reporter.stage("validacion")
    with stage_timer(metrics, "validacion"):
        from .validate import parseable_messages, validate_columns

        validate_columns(raw)
        raw = parseable_messages(raw)
        if raw.empty:
            raise ValueError("No hay filas procesables tras la validación")
    reporter.end("validacion")

    reporter.stage("preprocesamiento")
    with stage_timer(metrics, "preprocesamiento"):
        valid, preprocess_stats = preprocess.preprocess(raw, max_workers=settings.max_workers_cpu)
        if valid.empty:
            raise ValueError("Todas las filas fueron descartadas en preprocesamiento")
    reporter.end("preprocesamiento")

    reporter.stage("extraccion")
    with stage_timer(metrics, "extraccion"):
        valid = _extract_fields(valid, max_workers=settings.max_workers_cpu)
    reporter.end("extraccion")

    reporter.stage("tokens_original")
    with stage_timer(metrics, "tokens_original"):
        valid = _count_tokens_column(valid, "mensaje_texto", settings.batch_size)
    reporter.end("tokens_original")

    reporter.stage("tokens_limpio")
    with stage_timer(metrics, "tokens_limpio"):
        valid = _count_tokens_column(valid, "mensaje_limpio", settings.batch_size)
    reporter.end("tokens_limpio")

    translate_engine = "none"
    if settings.optimize_tokens:
        translator = build_translator(settings.translate_engine, settings.model_dir)
        reporter.stage("traduccion")
        with stage_timer(metrics, "traduccion"):
            valid, _cache = _translate_with_cache(
                valid,
                settings,
                translator,
                on_batch=lambda done, total: reporter.sub(done / total if total else 1.0),
            )
            translate_engine = translator.engine
        reporter.end("traduccion")
        reporter.stage("tokens_ingles")
        with stage_timer(metrics, "tokens_ingles"):
            valid = _count_tokens_column(valid, "mensaje_ingles", settings.batch_size)
        reporter.end("tokens_ingles")
    else:
        valid["tokens_ingles"] = pd.NA
        valid["mensaje_ingles"] = ""

    reporter.stage("costeo")
    with stage_timer(metrics, "costeo"):
        valid["costo_estimado_original"] = valid["tokens_original"].map(cost_for)
        valid["costo_estimado_limpio"] = valid["tokens_limpio"].map(cost_for)
        valid["costo_estimado_ingles"] = valid["tokens_ingles"].map(cost_for)
    reporter.end("costeo")

    reporter.stage("reporte")
    with stage_timer(metrics, "reporte"):
        output = report.build_output_frame(valid)
        aggregates = report.compute_aggregates(valid)
        aggregates["preprocesamiento"] = preprocess_stats
        aggregates["_meta"] = {
            "motor_traduccion": translate_engine,
            "optimizar_tokens": settings.optimize_tokens,
            "tarifa_usd_por_millon": 2.50,
            "mensajes_por_dia_proyeccion": 15_000,
            "tiempos_seg": metrics.to_dict(),
        }
        report.write_excel(output, settings.output_excel)
        report.write_excel(output, Path(settings.output_excel).parent / "resultados.xlsx")
        _write_json(settings.output_json, aggregates)
    reporter.end("reporte")
    reporter.done()

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
