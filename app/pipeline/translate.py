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


def _translate_ctranslate2(texts: list[str], model_dir: str) -> list[str]:
    """Traducción local por lotes con ctranslate2 (modelo MarianMT convertido)."""
    if not _HAS_CTRANSLATE2:
        raise TranslationError("ctranslate2 no está instalado")
    # La tokenización se hace con el tokenizador SentencePiece del modelo MarianMT.
    try:
        tokenizer = transformers.AutoTokenizer.from_pretrained(model_dir)
    except Exception as exc:  # noqa: BLE001
        raise TranslationError(f"No se pudo cargar el tokenizador de {model_dir}: {exc}") from exc

    translator = ctranslate2.Translator(model_dir, device="cpu")
    results: list[str] = []
    # ctranslate2 consume token IDs; traducimos en lotes conservando orden.
    batch_ids = tokenizer(texts, return_tensors="pt", padding=True)["input_ids"]
    encoded = [ids.tolist() for ids in batch_ids]
    outputs = translator.translate_batch(encoded)
    for out, orig in zip(outputs, texts, strict=True):
        text = tokenizer.decode(out.hypotheses[0], skip_special_tokens=True)
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
            try:
                result = TranslationResult(
                    engine="ctranslate2", texts=_translate_ctranslate2(texts, self._model_dir)
                )
            except TranslationError as exc:
                log.warning("ctranslate2 no disponible (%s); fallback a deep_translator", exc)
                result = TranslationResult(engine="deep_translator", texts=_translate_deep_translator(texts))
            self.engine = result.engine
            return result
        result = TranslationResult(engine="deep_translator", texts=_translate_deep_translator(texts))
        self.engine = result.engine
        return result


def build_translator(engine: str, model_dir: str) -> Translator:
    """Construye un traductor según el motor elegido."""
    return Translator(engine, model_dir)
