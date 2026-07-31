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
    """Tokens de una lista de textos en un bucle sobre el encoder C/Rust.

    Se evita encode_batch: su ThreadPoolExecutor interno agrega overhead por item
    sin paralelizar (tiktoken no libera el GIL), y un bucle plano de encode es ~3x
    más rápido.
    """
    if not texts:
        return []
    enc = get_encoder()
    return [len(enc.encode(t)) for t in texts]

