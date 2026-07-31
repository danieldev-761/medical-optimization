"""Tests de la pipeline HU-015 (sin dependencia de red)."""

import pandas as pd
import pytest

from app.config import OUTPUT_COLUMNS, RATE_USD_PER_MILLION
from app.pipeline import cost, extract, preprocess, report, tokens, validate
from app.pipeline.ingest import consolidate, _discover_inputs


class TestValidate:
    def test_missing_columns_raise(self):
        df = pd.DataFrame({"foo": [1]})
        with pytest.raises(validate.ColumnValidationError):
            validate.validate_columns(df)

    def test_valid_columns_pass(self):
        df = pd.DataFrame({"paciente_id": ["1"], "mensaje_texto": ["hola"]})
        validate.validate_columns(df)


class TestPreprocess:
    def test_clean_removes_courtesies(self):
        text = "Hola buenos días, muchas gracias por confirmar la cita por favor."
        cleaned = preprocess.clean_message(text)
        assert "confirmar" in cleaned
        assert "gracias" not in cleaned

    def test_clean_preserves_intent(self):
        text = "Necesito reprogramar mi cita para el viernes por la tarde."
        cleaned = preprocess.clean_message(text)
        assert "reprogramar" in cleaned
        assert "viernes" in cleaned

    def test_filter_empty(self):
        df = pd.DataFrame({"mensaje_texto": ["confirmo", "", "   ", "hola"]})
        valid, discarded = preprocess.filter_usable(df)
        assert len(valid) == 1
        assert len(discarded) == 3

    def test_deduplicate(self):
        df = pd.DataFrame({"mensaje_texto": ["Confirmo mi cita", "confirmo  mi  cita", "cancelar"]})
        out = preprocess.deduplicate(df)
        assert len(out) == 2


class TestExtract:
    def test_accion_confirmar(self):
        assert extract.extract_accion("Quiero confirmar mi cita") == "confirmar"

    def test_accion_cancelar(self):
        assert extract.extract_accion("No voy a poder asistir, cancele por favor") == "cancelar"

    def test_accion_reprogramar(self):
        assert extract.extract_accion("Quiero cambiar la fecha de mi cita") == "reprogramar"

    def test_especialidad(self):
        assert extract.extract_especialidad("cita con el cardiologo") == "cardiologia"
        assert extract.extract_especialidad("consulta de dermatologia") == "dermatologia"

    def test_fecha_y_horario(self):
        text = "confirmo la cita el 15 de mayo a las 9 am"
        assert "15 de mayo" in extract.extract_fecha_solicitada(text)
        assert "9 am" in extract.extract_preferencia_horario(text)


class TestTokens:
    def test_count(self):
        assert tokens.count_tokens("hola") > 0
        assert tokens.count_tokens("") == 0

    def test_batch_matches_single(self):
        texts = ["hola mundo", "cancelar cita", ""]
        assert tokens.count_tokens_batch(texts) == [tokens.count_tokens(t) for t in texts]


class TestCost:
    def test_formula(self):
        assert cost.cost_for(1_000_000) == pytest.approx(RATE_USD_PER_MILLION)
        assert cost.cost_for(0) == 0.0

    def test_projection(self):
        p = cost.project_cost(20.0, 30)
        assert p["mensajes"] == 450_000
        assert p["tokens"] == 9_000_000
        assert p["costo"] == pytest.approx(22.5)


class TestReport:
    def test_output_columns_contract(self):
        processed = pd.DataFrame(
            {
                "paciente_id": ["P1", "P2"],
                "accion": ["confirmar", "cancelar"],
                "especialidad": ["", "dermatologia"],
                "fecha_solicitada": ["lunes", ""],
                "preferencia_horario": ["", "por la tarde"],
                "tokens_original": [10, 12],
                "tokens_limpio": [9, 11],
                "tokens_ingles": [8, 10],
                "costo_estimado_original": [0.0, 0.0],
                "costo_estimado_limpio": [0.0, 0.0],
                "costo_estimado_ingles": [0.0, 0.0],
            }
        )
        out = report.build_output_frame(processed)
        assert list(out.columns) == OUTPUT_COLUMNS

    def test_aggregates(self):
        processed = pd.DataFrame(
            {
                "tokens_original": [100, 200],
                "tokens_limpio": [80, 160],
                "tokens_ingles": [60, 120],
                "accion": ["confirmar", "cancelar"],
                "especialidad": ["", "x"],
            }
        )
        agg = report.compute_aggregates(processed)
        assert agg["totales"]["tokens_original"] == 300
        assert agg["totales"]["costo_original"] == pytest.approx(300 / 1_000_000 * 2.5)
        assert "proyeccion" in agg
        assert agg["proyeccion"]["original"]["anual"]["costo"] > 0


class TestIngest:
    def test_consolidate_preserves_source(self, tmp_path):
        files = [tmp_path / "a.xlsx", tmp_path / "b.xlsx"]
        frames = [
            pd.DataFrame({"paciente_id": ["1"], "mensaje_texto": ["x"]}),
            pd.DataFrame({"paciente_id": ["2"], "mensaje_texto": ["y"]}),
        ]
        out = consolidate(frames, files)
        assert len(out) == 2
        assert out["archivo_origen"].nunique() == 2

    def test_discover_dir(self, tmp_path):
        (tmp_path / "a.xlsx").touch()
        (tmp_path / "b.xlsx").touch()
        files = _discover_inputs(tmp_path)
        assert len(files) == 2

    def test_discover_invalid_ext(self, tmp_path):
        bad = tmp_path / "x.csv"
        bad.touch()
        with pytest.raises(ValueError):
            _discover_inputs(bad)
