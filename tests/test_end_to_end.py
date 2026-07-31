"""Test end-to-end de la pipeline sin red (optimizar_tokens=False)."""

import pandas as pd

from app.config import Settings
from app.pipeline.pipeline import run_pipeline


def test_pipeline_end_to_end_no_optimize(tmp_path):
    xlsx = tmp_path / "input.xlsx"
    pd.DataFrame(
        {
            "paciente_id": ["P1", "P2", "P3", "P4"],
            "mensaje_texto": [
                "Quiero confirmar mi cita de cardiologia para el lunes.",
                "Necesito cancelar la cita, no asistire.",
                "",
                "hola",
            ],
        }
    ).to_excel(xlsx, index=False)

    out_excel = tmp_path / "out" / "resultados.xlsx"
    settings = Settings(
        input_path=str(xlsx),
        output_excel=str(out_excel),
        output_json=str(tmp_path / "out" / "agregados.json"),
        output_csv=str(tmp_path / "out" / "intermediate.csv"),
        metrics_path=str(tmp_path / "out" / "metrics.json"),
        optimize_tokens=False,
    )

    result = run_pipeline(settings)

    assert result.preprocess_stats["filas_leidas"] == 4
    assert result.preprocess_stats["filas_validas"] == 2
    assert result.output_frame["tokens_ingles"].fillna(0).sum() == 0
    assert list(result.output_frame.columns) == list(pd.read_excel(out_excel).columns)
    assert result.aggregates["_meta"]["optimizar_tokens"] is False
    assert result.aggregates["_meta"]["motor_traduccion"] == "none"
    assert "ingles" not in result.aggregates["proyeccion"]
    assert result.aggregates["proyeccion"]["original"]["anual"]["costo"] > 0
