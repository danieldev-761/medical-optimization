"""API FastAPI: sirve el dashboard y expone /api/analyze para procesar archivos."""

import json
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .pipeline.pipeline import run_pipeline

STATIC_DIR = Path(__file__).parent / "static"
OUT_DIR = Path("out")
OUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Medical Opt · HU-015", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/results")
def latest_results() -> JSONResponse:
    """Devuelve los últimos agregados generados por run.py o /api/analyze."""
    path = OUT_DIR / "agregados.json"
    if not path.exists():
        raise HTTPException(404, "Aún no hay resultados. Ejecuta run.py o sube un archivo.")
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("_meta", {})["ultima_ejecucion"] = path.stat().st_mtime
    return JSONResponse(data)


@app.post("/api/analyze")
def analyze(
    file: UploadFile = File(...),
    optimize_tokens: bool = Query(True, description="optimizar_tokens"),
    engine: str = Query("auto", pattern="^(ctranslate2|deep_translator|auto)$"),
    batch_size: int = Query(500, ge=1),
) -> JSONResponse:
    """Procesa un archivo .xlsx subido y devuelve agregados + enlace al Excel."""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400, "El archivo debe ser .xlsx")

    run_id = uuid.uuid4().hex[:8]
    tmp = Path(tempfile.gettempdir()) / f"hu015_{run_id}"
    tmp.mkdir(parents=True, exist_ok=True)
    saved = tmp / file.filename
    with saved.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    settings = Settings(
        input_path=str(saved),
        output_excel=str(OUT_DIR / "resultados.xlsx"),
        output_json=str(OUT_DIR / "agregados.json"),
        optimize_tokens=optimize_tokens,
        batch_size=batch_size,
        translate_engine=engine,
    )
    try:
        result = run_pipeline(settings)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Error procesando el archivo: {exc}") from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    aggregates = result.aggregates
    aggregates["_meta"]["archivo"] = file.filename
    aggregates["_meta"]["ejecutado_via"] = "api"
    return JSONResponse(aggregates)


@app.get("/api/download")
def download_excel() -> FileResponse:
    path = OUT_DIR / "resultados.xlsx"
    if not path.exists():
        raise HTTPException(404, "Aún no hay Excel generado.")
    return FileResponse(str(path), filename="resultados.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
