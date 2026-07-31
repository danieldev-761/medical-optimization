# Medical Opt · HU-015

Pipeline por etapas para procesar solicitudes de citas médicas desde `.xlsx`
(archivo único o carpeta), evaluar tokenización en español vs. inglés y producir
un Excel estructurado más un dashboard con KPIs, costos y proyecciones.

## Stack

Python 3.11+ · `pandas`/`openpyxl` · `tiktoken` (o200k_base) · `ctranslate2`
(traducción local) con fallback `deep-translator` · `FastAPI` + `uvicorn`.

## Instalación

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### Traducción local sin red (recomendado)

El motor `ctranslate2` traduce en local (sin llamadas de red) y es ~3.6× más rápido
que el fallback de Google. Para disponibilizarlo:

```bash
pip install -r requirements-convert.txt   # solo para la conversión (incluye torch CPU)
python scripts/setup_ctranslate2_model.py
```

Descarga `Helsinki-NLP/opus-mt-es-en` (~300 MB una sola vez) y lo convierte a
formato CTranslate2 en `models/opus-mt-es-en`. Con el modelo presente, el motor
`auto` usa ctranslate2 automáticamente; sin él, degrada a `deep_translator`.

## Uso

### CLI (archivo único o carpeta)

```bash
python run.py sample                    # modo optimizar_tokens=True, motor auto
python run.py sample --no-optimize      # solo texto original en español
python run.py ruta/archivo.xlsx --engine ctranslate2   # forzar traducción local
```

Salidas en `out/`: `resultados.xlsx` (1 hoja), `agregados.json`, `metrics.json`, `intermediate.csv`.

### Dashboard

```bash
python -m uvicorn app.main:app --port 8000
```

- `GET /` — dashboard (KPIs, gráficas, proyección hipotética @ 15,000 msgs/día).
- `POST /api/analyze` — sube un `.xlsx` y ejecuta la pipeline en vivo.
- `GET /api/results` — últimos agregados generados.
- `GET /api/download` — último Excel generado.

### Datos de muestra

```bash
python scripts/make_sample.py --n 400 --files 2
```

## Arquitectura

```
app/
  main.py              # FastAPI: dashboard, /api/analyze, /api/results, /api/download
  static/              # frontend (HTML + Chart.js, sin framework)
  config.py            # contrato de salida, tarifa, proyección, batch/workers
  pipeline/
    ingest.py          # .xlsx único o carpeta -> consolidación -> CSV intermedio
    validate.py        # columnas obligatorias (paciente_id, mensaje_texto)
    preprocess.py      # filtrado de vacíos, limpieza semántica, dedup
    extract.py         # heurísticas/regex: accion, especialidad, fecha, horario
    tokens.py          # tokenización o200k_base por batches
    translate.py       # ctranslate2 local + fallback deep_translator
    cost.py            # 2.50 USD / 1M tokens + proyección por periodos
    report.py          # Excel final (1 hoja) + agregados
    pipeline.py        # orquestador por etapas con timing y caché
    metrics.py         # instrumentación de tiempos por etapa
```

## Rendimiento

- Conversión temprana a CSV y análisis exclusivo sobre `mensaje_texto`.
- Reducción de volumen (filtrado + dedup) antes de las etapas costosas.
- `ThreadPoolExecutor` solo en I/O: lectura de archivos y traducción (8 workers).
- Batches de 500 filas para limpieza/tokenización; caché por texto limpio.
- Profiling por etapa en `out/metrics.json` y en el dashboard.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Los tests no requieren red (el modo `optimizar_tokens=False` no traduce).
