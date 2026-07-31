"""CLI: ejecuta la pipeline completa sin servidor.

Uso:
    python run.py sample [--no-optimize] [--out out/resultados.xlsx] [--engine ctranslate2|deep_translator|auto]
"""

import argparse
import json
import logging

from app.config import Settings
from app.pipeline.pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline HU-015 de citas médicas")
    parser.add_argument("input", help="Archivo .xlsx o carpeta con .xlsx")
    parser.add_argument("--out-excel", default="out/resultados.xlsx")
    parser.add_argument("--out-json", default="out/agregados.json")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--no-optimize", action="store_true", help="optimizar_tokens=False")
    parser.add_argument("--engine", choices=["ctranslate2", "deep_translator", "auto"], default="auto")
    parser.add_argument("--model-dir", default="models/opus-mt-es-en")
    args = parser.parse_args()

    settings = Settings(
        input_path=args.input,
        output_excel=args.out_excel,
        output_json=args.out_json,
        optimize_tokens=not args.no_optimize,
        batch_size=args.batch_size,
        translate_engine=args.engine,
        model_dir=args.model_dir,
    )
    result = run_pipeline(settings)

    print("\n=== Resumen ===")
    print(json.dumps(result.preprocess_stats, indent=2))
    print("\n=== Tiempos por etapa (s) ===")
    print(json.dumps(result.metrics.to_dict(), indent=2))
    print("\n=== Agregados ===")
    print(json.dumps(result.aggregates, indent=2, ensure_ascii=False))
    print(f"\nMotor de traducción: {result.translate_engine}")
    print(f"Excel: {settings.output_excel}")
    print(f"JSON:  {settings.output_json}")


if __name__ == "__main__":
    main()
