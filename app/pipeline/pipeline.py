"""Orquestador de la pipeline HU-015 por etapas, con timing y caché."""

import json
import logging
import math
import shutil
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import pandas as pd

from ..config import Settings
from . import extract, ingest, preprocess, report, tokens
from .cost import cost_for
from .metrics import Metrics, stage_timer
from .progress import ProgressListener, ProgressReporter
from .translate import build_translator

log = logging.getLogger(__name__)

EXTRACT_FIELDS = ("accion", "especialidad", "fecha_solicitada", "preferencia_horario")


@dataclass
class PipelineResult:
    settings: Settings
    output_frame: pd.DataFrame
    aggregates: dict
    preprocess_stats: dict
    metrics: Metrics
    discarded: pd.DataFrame
    translate_engine: str = "none"


def _needed_extract_fields(frame: pd.DataFrame) -> list[str]:
    """Campos a extraer: los ausentes o parcialmente vacíos en el input.

    Si el input ya provee un campo completo, se preserva tal cual (input gana)
    y se evita el costo de extraerlo.
    """
    needed = []
    for col in EXTRACT_FIELDS:
        if col in frame.columns:
            if frame[col].fillna("").astype(str).str.strip().eq("").any():
                needed.append(col)
        else:
            needed.append(col)
    return needed


def _merge_extracted(frame: pd.DataFrame, extracted_rows: list[dict], fields: list[str]) -> pd.DataFrame:
    """Fusiona los campos extraídos con precedencia del input (solo rellena vacíos)."""
    for col in fields:
        values = [row[col] for row in extracted_rows]
        if col in frame.columns:
            existing = frame[col].fillna("").astype(str)
            frame[col] = [pv if pv.strip() else ev for pv, ev in zip(existing.tolist(), values)]
        else:
            frame[col] = values
    return frame


def _clean_extract_chunk(chunk_texts: list[str], fields: list[str]) -> list[tuple[str, dict]]:
    """Helper global serializable para ProcessPoolExecutor: limpia y extrae en un solo pase."""
    return [(preprocess.clean_message(t), extract.extract_fields(t, fields)) for t in chunk_texts]


def _fused_clean_extract(texts: list[str], fields: list[str], max_workers: int) -> tuple[list[str], list[dict]]:
    """Limpieza + extracción en un único pase paralelo (una sola ronda de IPC)."""
    n = len(texts)
    if n > 100 and max_workers > 1:
        chunk_size = math.ceil(n / max_workers)
        chunks = [texts[i : i + chunk_size] for i in range(0, n, chunk_size)]
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results_nested = list(pool.map(partial(_clean_extract_chunk, fields=fields), chunks))
        items = [item for sublist in results_nested for item in sublist]
    else:
        items = _clean_extract_chunk(texts, fields)
    return [c for c, _ in items], [e for _, e in items]


def _count_chunk(chunk_texts: list[str]) -> list[int]:
    """Helper global serializable para ProcessPoolExecutor."""
    return tokens.count_tokens_batch(chunk_texts)


def _count_tokens_parallel(texts: list[str], max_workers: int) -> list[int]:
    """Tokeniza una lista de textos en paralelo por CPU (bypass del GIL)."""
    n = len(texts)
    if n > 100 and max_workers > 1:
        tokens.get_encoder()
        chunk_size = math.ceil(n / max_workers)
        chunks = [texts[i : i + chunk_size] for i in range(0, n, chunk_size)]
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(_count_chunk, chunks))
        return [x for sub in results for x in sub]
    return tokens.count_tokens_batch(texts)


def _count_tokens_column(frame: pd.DataFrame, column: str, max_workers: int) -> pd.DataFrame:
    """Tokeniza una columna paralelizada y la asigna como tokens_<sufijo>."""
    suffix = {"mensaje_texto": "original", "mensaje_limpio": "limpio", "mensaje_ingles": "ingles"}[column]
    texts = frame[column].fillna("").astype(str).tolist()
    frame[f"tokens_{suffix}"] = _count_tokens_parallel(texts, max_workers)
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
        texts = raw["mensaje_texto"].fillna("").astype(str).tolist()
        fields = _needed_extract_fields(raw)
        cleaned, extracted_rows = _fused_clean_extract(texts, fields, settings.max_workers_cpu)
        raw = _merge_extracted(raw, extracted_rows, fields)
        valid, preprocess_stats = preprocess.preprocess(
            raw, max_workers=settings.max_workers_cpu, cleaned_texts=cleaned
        )
    reporter.end("preprocesamiento")

    reporter.stage("tokens_original")
    with stage_timer(metrics, "tokens_original"):
        valid = _count_tokens_column(valid, "mensaje_texto", settings.max_workers_cpu)
    reporter.end("tokens_original")

    reporter.stage("tokens_limpio")
    with stage_timer(metrics, "tokens_limpio"):
        valid = _count_tokens_column(valid, "mensaje_limpio", settings.max_workers_cpu)
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
            valid = _count_tokens_column(valid, "mensaje_ingles", settings.max_workers_cpu)
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
        default_excel = Path(settings.output_excel).parent / "resultados.xlsx"
        if default_excel.resolve() != Path(settings.output_excel).resolve():
            shutil.copy2(settings.output_excel, default_excel)
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
