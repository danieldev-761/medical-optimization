"""Descarga y convierte el modelo MarianMT ES->EN a formato CTranslate2.

Uso:
    python scripts/setup_ctranslate2_model.py [--model Helsinki-NLP/opus-mt-es-en] [--out models/opus-mt-es-en]

Tras ejecutarlo, la traducción local queda disponible sin red.
"""

import argparse
import logging
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("setup_model")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convierte opus-mt-es-en a CTranslate2")
    parser.add_argument("--model", default="Helsinki-NLP/opus-mt-es-en")
    parser.add_argument("--out", default="models/opus-mt-es-en")
    args = parser.parse_args()

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)

    import ctranslate2
    from transformers import MarianTokenizer

    log.info("Descargando tokenizador y modelo %s ...", args.model)
    tokenizer = MarianTokenizer.from_pretrained(args.model)

    log.info("Convirtiendo a CTranslate2 (CPU) ...")
    converter = ctranslate2.converters.TransformersConverter(args.model)
    converter.convert(str(out), quantization="int8")

    log.info("Guardando tokenizador junto al modelo ...")
    tokenizer.save_pretrained(str(out))

    log.info("Modelo listo en: %s", out)


if __name__ == "__main__":
    main()
