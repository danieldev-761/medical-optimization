"""Caché persistente con Redis para el pipeline de traducción ES -> EN.

Soporta operaciones masivas MGET / MSET y degradación transparente a caché local.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings

log = logging.getLogger(__name__)

try:
    import redis
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False


class TranslationCache:
    """Gestor de caché híbrido (Redis + memoria local)."""

    def __init__(self, settings: Settings):
        self.enabled = settings.cache_enabled
        self.ttl_seconds = settings.redis_ttl_days * 86400 if settings.redis_ttl_days > 0 else None
        self._local_cache: dict[str, str] = {}
        self._client: redis.Redis | None = None

        if self.enabled and settings.redis_enabled and _HAS_REDIS:
            try:
                client = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    socket_timeout=1.5,
                    socket_connect_timeout=1.5,
                    decode_responses=True,
                )
                client.ping()
                self._client = client
                log.info("Conexión con Redis establecida exitosamente (%s:%d)", settings.redis_host, settings.redis_port)
            except Exception as exc:  # noqa: BLE001
                log.warning("No se pudo conectar a Redis (%s). Se usará memoria local.", exc)
                self._client = None
        elif self.enabled and not _HAS_REDIS:
            log.warning("Librería 'redis' no instalada. Usando memoria local.")

    @staticmethod
    def _make_key(text: str) -> str:
        """Genera una clave hash SHA256 corta con prefijo para el texto."""
        return "tr_es_en:" + hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]

    def get_many(self, texts: list[str]) -> dict[str, str]:
        """Recupera un diccionario {texto_original: texto_traducido} desde la caché."""
        if not texts or not self.enabled:
            return {}

        results: dict[str, str] = {}
        missing_texts: list[str] = []

        # 1. Buscar en caché local
        for text in texts:
            if text in self._local_cache:
                results[text] = self._local_cache[text]
            else:
                missing_texts.append(text)

        if not missing_texts or self._client is None:
            return results

        # 2. Buscar pendientes en Redis vía MGET
        try:
            keys = [self._make_key(t) for t in missing_texts]
            redis_values = self._client.mget(keys)
            for text, val in zip(missing_texts, redis_values, strict=True):
                if val is not None:
                    results[text] = val
                    self._local_cache[text] = val
        except Exception as exc:  # noqa: BLE001
            log.warning("Error leyendo de Redis: %s", exc)

        return results

    def set_many(self, translations: dict[str, str]) -> None:
        """Guarda pares de traducción {texto_original: texto_traducido} en caché."""
        if not translations or not self.enabled:
            return

        # 1. Guardar en caché local
        self._local_cache.update(translations)

        if self._client is None:
            return

        # 2. Guardar en Redis vía Pipeline
        try:
            pipe = self._client.pipeline(transaction=False)
            for text, translated in translations.items():
                if text and translated:
                    key = self._make_key(text)
                    if self.ttl_seconds:
                        pipe.setex(key, self.ttl_seconds, translated)
                    else:
                        pipe.set(key, translated)
            pipe.execute()
        except Exception as exc:  # noqa: BLE001
            log.warning("Error escribiendo en Redis: %s", exc)
