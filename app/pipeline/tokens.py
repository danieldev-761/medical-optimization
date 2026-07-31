"""Tokenización con tiktoken, encoding o200k_base (local, CPU-bound)."""

import tiktoken

_ENCODER: tiktoken.Encoding | None = None


def get_encoder() -> tiktoken.Encoding:
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("o200k_base")
    return _ENCODER


def count_tokens(text: str) -> int:
    """Tokens de un texto con o200k_base. Texto vacío -> 0."""
    if not text:
        return 0
    return len(get_encoder().encode(text))


def count_tokens_batch(texts: list[str]) -> list[int]:
    """Tokens de una lista de textos en una sola llamada al encoder."""
    if not texts:
        return []
    return [len(t) for t in get_encoder().encode_batch(texts)]
