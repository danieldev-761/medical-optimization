"""Traducción ES->EN de mensaje_texto limpio.

Motores:
- ctranslate2: traducción local CPU por lotes, sin red, con modelo CTranslate2
  ES->EN (p. ej. opus-mt-es-en convertido). Si el modelo no está disponible o
  no puede cargarse, se degrada a deep_translator.
- deep_translator: Google Translate gratuito vía red (I/O-bound, usa batches).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

try:
    import ctranslate2  # type: ignore
    import transformers  # type: ignore
    _HAS_CTRANSLATE2 = True
except ImportError:  # pragma: no cover
    _HAS_CTRANSLATE2 = False


@dataclass
class TranslationResult:
    engine: str
    texts: list[str]


class TranslationError(RuntimeError):
    pass


def _ctranslate2_available(model_dir: str) -> bool:
    """True si el modelo CTranslate2 local está presente y utilizable."""
    if not _HAS_CTRANSLATE2:
        return False
    model_file = Path(model_dir) / "model.bin"
    return model_file.is_file()


_CACHED_TOKENIZER = None
_CACHED_TRANSLATOR = None
_CACHED_MODEL_DIR = None


def _translate_ctranslate2(texts: list[str], model_dir: str) -> list[str]:
    """Traducción local por lotes ultrarrápida con ctranslate2."""
    global _CACHED_TOKENIZER, _CACHED_TRANSLATOR, _CACHED_MODEL_DIR
    if not _HAS_CTRANSLATE2:
        raise TranslationError("ctranslate2 no está instalado")

    if _CACHED_TRANSLATOR is None or _CACHED_MODEL_DIR != model_dir:
        import os
        num_cores = os.cpu_count() or 4
        try:
            try:
                _CACHED_TOKENIZER = transformers.AutoTokenizer.from_pretrained(model_dir, use_fast=False, local_files_only=True)
            except Exception:
                _CACHED_TOKENIZER = transformers.AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-es-en", use_fast=False, local_files_only=True)
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(f"No se pudo cargar el tokenizador de {model_dir}: {exc}") from exc

        _CACHED_TRANSLATOR = ctranslate2.Translator(
            model_dir,
            device="cpu",
            inter_threads=num_cores,
            intra_threads=2,
        )
        _CACHED_MODEL_DIR = model_dir

    tokenizer = _CACHED_TOKENIZER
    translator = _CACHED_TRANSLATOR

    if not texts:
        return []

    # Tokenización vectorizada batch con C++/Rust fast tokenizer
    encoded = tokenizer(texts, add_special_tokens=True)
    input_ids = encoded["input_ids"]
    tokenized = [tokenizer.convert_ids_to_tokens(ids) for ids in input_ids]

    outputs = translator.translate_batch(
        tokenized,
        beam_size=1,
        max_batch_size=1024,
        batch_type="tokens",
    )

    results: list[str] = []
    for out, orig in zip(outputs, texts, strict=True):
        text = tokenizer.convert_tokens_to_string(out.hypotheses[0]).strip()
        results.append(text if text else orig)
    return results


def _translate_deep_translator(texts: list[str]) -> list[str]:
    """Traducción con Google Translate (gratis) en un único request por batch."""
    try:
        from deep_translator import GoogleTranslator
    except ImportError as exc:  # pragma: no cover
        raise TranslationError("deep-translator no está instalado") from exc
    if not texts:
        return []
    translator = GoogleTranslator(source="es", target="en")
    try:
        translated = translator.translate_batch(texts)
    except Exception as exc:  # noqa: BLE001
        raise TranslationError(f"deep_translator falló: {exc}") from exc
    return [t if t else orig for t, orig in zip(translated, texts, strict=True)]


class Translator:
    """Traductor con motor resoluble en runtime y fallback automático."""

    def __init__(self, engine: str, model_dir: str):
        if engine == "auto":
            engine = "ctranslate2" if _ctranslate2_available(model_dir) else "deep_translator"
        if engine == "ctranslate2" and not _HAS_CTRANSLATE2:
            log.warning("ctranslate2 requerido pero no instalado; se usa deep_translator")
            engine = "deep_translator"
        self._engine = engine
        self._model_dir = model_dir
        self.engine = engine

    def translate(self, texts: list[str]) -> TranslationResult:
        if not texts:
            return TranslationResult(engine=self.engine, texts=[])
        if self._engine == "ctranslate2":
            result = TranslationResult(
                engine="ctranslate2", texts=_translate_ctranslate2(texts, self._model_dir)
            )
            self.engine = result.engine
            return result
        result = TranslationResult(engine="deep_translator", texts=_translate_deep_translator(texts))
        self.engine = result.engine
        return result


def build_translator(engine: str, model_dir: str) -> Translator:
    """Construye un traductor según el motor elegido."""
    return Translator(engine, model_dir)
