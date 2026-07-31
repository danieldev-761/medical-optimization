"""Pruebas unitarias para el módulo de caché persistente con Redis y fallback local."""

from app.config import Settings
from app.pipeline.cache import TranslationCache


def test_translation_cache_local_fallback():
    settings = Settings(input_path="dummy.xlsx", redis_enabled=False)
    cache = TranslationCache(settings)

    texts = ["Hola mundo", "Quiero agendar cita"]
    # 1. Caché vacía
    assert cache.get_many(texts) == {}

    # 2. Guardar traducciones
    translations = {"Hola mundo": "Hello world", "Quiero agendar cita": "I want to schedule an appointment"}
    cache.set_many(translations)

    # 3. Leer de caché
    res = cache.get_many(texts)
    assert res == translations
