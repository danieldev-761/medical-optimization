# Medical Opt · HU-015

Pipeline por etapas para procesar solicitudes de citas médicas desde archivos
`.xlsx` (archivo único o carpeta), evaluar la optimización de tokens en español
vs. inglés y producir un Excel estructurado más un dashboard analítico con KPIs,
costos y proyecciones.

Diseñado para **rapidez de ejecución** sobre cargas masivas: CSV como formato
intermedio, saneamiento temprano, análisis exclusivo de la columna `mensaje_texto`
y concurrencia controlada solo en tareas I/O-bound.

---

## Índice

- [Stack](#stack)
- [Características](#características)
- [Instalación](#instalación)
- [Traducción local sin red](#traducción-local-sin-red-recomendado)
- [Datos de muestra](#datos-de-muestra)
- [Uso](#uso)
  - [CLI](#cli-archivo-único-o-carpeta)
  - [Dashboard (FastAPI)](#dashboard-fastapi)
  - [API](#api)
- [Modo `optimizar_tokens`](#modo-optimizar_tokens)
- [Contrato de salida (Excel)](#contrato-de-salida-excel)
- [Arquitectura](#arquitectura)
- [Rendimiento](#rendimiento)
- [Tests](#tests)
- [Documentación técnica](#documentación-técnica)
- [Solución de problemas](#solución-de-problemas)

---

## Stack

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ (probado en 3.14) |
| Datos | `pandas`, `openpyxl` |
| Tokenización | `tiktoken` (encoding `o200k_base`) |
| Traducción | `ctranslate2` (local, recomendado) + fallback `deep-translator` |
| Conversión de modelo | `transformers`, `torch` (CPU, solo setup) |
| API | `FastAPI`, `uvicorn` |
| Frontend | HTML/CSS/JS vanilla + Chart.js (sin framework) |
| Datos de muestra | `faker` |

---

## Características

- **Entrada flexible**: un `.xlsx` único o una carpeta con varios `.xlsx`, consolidados antes del análisis.
- **Validación temprana**: columnas obligatorias (`paciente_id` y `mensaje_texto`) validadas antes de cualquier procesamiento semántico; acepta el alias `id_paciente`.
- **Reducción de volumen**: filas vacías/nulas descartadas y mensajes normalizados deduplicados antes de las etapas costosas.
- **Limpieza semántica conservadora** solo sobre `mensaje_texto` (preserva intención, especialidad, fecha y horario).
- **Extracción heurística** (sin LLM, sin costo): `accion` (confirmar/cancelar/reprogramar), `especialidad`, `fecha_solicitada`, `preferencia_horario`.
- **Dos modos**: `optimizar_tokens=True` (original + limpio + inglés) o `False` (solo original en español).
- **Excel final de una sola hoja** con el contrato exacto de columnas.
- **Dashboard con flujo correcto**: subir archivo → progreso en tiempo real (SSE) → análisis recién generado. No muestra datos precargados.
- **Análisis económico**: costos con tarifa de 2.50 USD / 1M tokens, ahorro real y proyección hipotética a 15,000 mensajes/día (diario, mensual, trimestral, anual).
- **Profiling**: tiempos por etapa en `out/metrics.json` y en el dashboard.

---

## Instalación

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Traducción local sin red (recomendado)

El motor `ctranslate2` traduce 100 % en local (sin llamadas de red) y es
~3.6× más rápido que el fallback de Google. Para disponibilizarlo:

```bash
pip install -r requirements-convert.txt     # solo para la conversión (incluye torch CPU)
python scripts/setup_ctranslate2_model.py   # descarga y convierte el modelo
```

Descarga `Helsinki-NLP/opus-mt-es-en` (~300 MB, una sola vez) y lo convierte a
formato CTranslate2 (int8) en `models/opus-mt-es-en`. Con el modelo presente, el
motor `auto` usa ctranslate2 automáticamente; sin él, degrada a `deep_translator`.

> `models/` está en `.gitignore` (peso ~300 MB) y no se versiona.

---

## Datos de muestra

```bash
python scripts/generate_citas.py   # genera citas_medicas_solicitudes.xlsx (10,000 filas)
```

El generador usa Faker en español con formato `id_paciente` + `mensaje_texto`
(10 % de mensajes vacíos, 12 especialidades y vocabulario formal/médico). La
validación normaliza automáticamente `id_paciente` → `paciente_id`.

Ya existe `sample/citas_medicas_solicitudes.xlsx` con 10,000 filas listo para usar.

---

## Uso

### CLI (archivo único o carpeta)

```bash
python run.py sample                    # modo optimizar_tokens=True, motor auto
python run.py sample --no-optimize      # solo texto original en español (sin traducción)
python run.py ruta/archivo.xlsx --engine ctranslate2   # forzar traducción local
python run.py ruta/carpeta --batch-size 1000          # ajustar batch
```

Argumentos de `run.py`:

| Argumento | Default | Descripción |
|---|---|---|
| `input` (posicional) | — | Archivo `.xlsx` o carpeta con `.xlsx` |
| `--out-excel` | `out/resultados.xlsx` | Excel de salida |
| `--out-json` | `out/agregados.json` | Agregados JSON |
| `--batch-size` | `500` | Filas por batch |
| `--no-optimize` | — | `optimizar_tokens=False` |
| `--engine` | `auto` | `ctranslate2`, `deep_translator` o `auto` |
| `--model-dir` | `models/opus-mt-es-en` | Ruta del modelo local |

Salidas en `out/`:

| Archivo | Contenido |
|---|---|
| `resultados.xlsx` | Excel final, 1 hoja (`Resultados`) |
| `agregados.json` | Agregados reales + proyección hipotética |
| `metrics.json` | Tiempos por etapa |
| `intermediate.csv` | Consolidado convertido a CSV (formato intermedio) |

### Dashboard (FastAPI)

```bash
python -m uvicorn app.main:app --port 8000
# abre http://127.0.0.1:8000
```

Flujo del dashboard:

1. Se muestra **Procesar archivo** (primera sección, sin datos precargados).
2. Arrastras o eliges un `.xlsx` y configuras `optimizar_tokens` y el motor.
3. La barra de progreso avanza en **tiempo real** etapa por etapa (ingesta,
   validación, preprocesamiento, extracción, tokens, traducción por lotes, costeo).
4. Al terminar, se renderiza el análisis: KPIs, variantes, ahorro, gráficas,
   profiling y proyección hipotética, con botón para descargar el Excel.

### API

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/` | Dashboard |
| `GET` | `/api/results` | Últimos agregados generados (`agregados.json`) |
| `POST` | `/api/analyze` | Procesa un `.xlsx` (multipart) y devuelve JSON al finalizar |
| `POST` | `/api/analyze/stream` | Igual que `/analyze` pero emite **progreso en vivo** vía SSE |
| `GET` | `/api/download` | Descarga el último Excel generado |

**SSE — eventos de `/api/analyze/stream`:**

```
data: {"type":"stage","etapa":"traduccion","progreso":45.2}
data: {"type":"done","data":{...agregados...}}
data: {"type":"error","detail":"..."}
```

Parámetros de `/api/analyze` y `/api/analyze/stream` (query):

| Parámetro | Default | Descripción |
|---|---|---|
| `optimize_tokens` | `true` | Activa variantes limpio/inglés |
| `engine` | `auto` | `ctranslate2` / `deep_translator` / `auto` |
| `batch_size` | `500` | Filas por batch |

Ejemplo con curl:

```bash
curl -N -X POST "http://127.0.0.1:8000/api/analyze/stream?engine=auto" \
  -F "file=@citas_medicas_solicitudes.xlsx"
```

---

## Modo `optimizar_tokens`

### `optimizar_tokens = False`

Solo validación de integridad y procesamiento del **texto original en español**.
No hay arbitraje de costo, comparación de variantes ni limpieza orientada a
reducción de tokens. `tokens_ingles` queda nulo y se excluye del análisis.

### `optimizar_tokens = True`

Ejecuta tres variantes del mismo `mensaje_texto`:

1. **Original** en español.
2. **Limpio** (optimizado) en español.
3. **Traducido al inglés** a partir de la versión limpia.

Se registran tokens y costos estimados de las tres variantes en el Excel y en el
dashboard. La traducción ocurre siempre sobre `mensaje_texto` limpio.

---

## Contrato de salida (Excel)

Una sola hoja (`Resultados`) con estas columnas, **en este orden exacto**:

| # | Columna | Descripción |
|---|---|---|
| 1 | `paciente_id` | Identificador del paciente |
| 2 | `accion` | `confirmar`, `cancelar` o `reprogramar` (vacío si no se detecta) |
| 3 | `especialidad` | Detectada en el mensaje (vacío si no aparece) |
| 4 | `fecha_solicitada` | Fecha o referencia temporal (vacío si no aparece) |
| 5 | `preferencia_horario` | Preferencia horaria (vacío si no aparece) |
| 6 | `tokens_original` | Tokens del texto original (`o200k_base`) |
| 7 | `tokens_limpio` | Tokens del texto limpio |
| 8 | `tokens_ingles` | Tokens del texto limpio traducido (nulo si `optimizar_tokens=False`) |
| 9 | `costo_estimado_original` | Costo estimado de la variante original |
| 10 | `costo_estimado_limpio` | Costo estimado de la variante limpia |
| 11 | `costo_estimado_ingles` | Costo estimado de la variante en inglés |

---

## Arquitectura

```
medical_opt/
├── app/
│   ├── main.py              # FastAPI: dashboard, /api/analyze(/stream), /api/results, /api/download
│   ├── config.py            # contrato de salida, tarifa, proyección, batch/workers
│   ├── static/              # frontend (index.html, style.css, app.js + Chart.js)
│   └── pipeline/
│       ├── ingest.py        # .xlsx único o carpeta -> consolidación -> CSV intermedio
│       ├── validate.py      # columnas obligatorias (paciente_id, mensaje_texto) + aliases
│       ├── preprocess.py    # filtrado de vacíos, limpieza semántica, dedup, batches
│       ├── extract.py       # heurísticas/regex: accion, especialidad, fecha, horario
│       ├── tokens.py        # tokenización o200k_base por batches
│       ├── translate.py     # ctranslate2 local + fallback deep_translator
│       ├── cost.py          # 2.50 USD / 1M tokens + proyección por periodos
│       ├── report.py        # Excel final (1 hoja) + agregados
│       ├── progress.py      # reporter de progreso ponderado para streaming SSE
│       ├── metrics.py       # instrumentación de tiempos por etapa
│       └── pipeline.py      # orquestador por etapas con timing y caché
├── scripts/
│   ├── generate_citas.py    # generador oficial de datos de muestra (Faker)
│   └── setup_ctranslate2_model.py  # conversión del modelo de traducción local
├── tests/
│   ├── test_pipeline.py     # tests unitarios por etapa
│   └── test_end_to_end.py   # test integral sin red
├── models/                  # (gitignored) modelo CTranslate2 local
├── run.py                   # CLI del pipeline completo sin servidor
├── requirements.txt         # dependencias de runtime
├── requirements-dev.txt     # dependencias de desarrollo/tests
├── requirements-convert.txt # solo para convertir el modelo (torch)
└── docs/documento_tecnico.md  # documentación técnica detallada
```

---

## Rendimiento

- **CSV temprano**: los `.xlsx` se convierten a CSV inmediatamente tras la lectura para reducir el costo de procesamiento posterior.
- **Análisis focalizado**: limpieza, tokenización y traducción operan solo sobre `mensaje_texto`.
- **Reducción antes de lo costoso**: filtrado de vacíos y dedup de mensajes normalizados antes de tokenizar/traducir.
- **Concurrencia I/O-bound** (`ThreadPoolExecutor`):
  - `max_workers=4` para lectura concurrente de múltiples archivos.
  - `max_workers=8` para traducción (ctranslate2 batches / deep_translator).
- **Batches** de 500–1000 filas para limpieza y tokenización local.
- **Caché** por texto limpio para no re-traducir mensajes equivalentes.
- **Instrumentación**: tiempos por etapa en `out/metrics.json` y dashboard.

**Medición de referencia** (10,000 filas, motor ctranslate2 local):

| Etapa | Tiempo |
|---|---|
| Ingesta | 1.09 s |
| Preprocesamiento | 0.95 s |
| Extracción | 2.23 s |
| Tokens (3 variantes) | ~1.9 s |
| Traducción (8,980 mensajes) | 246.8 s |
| Reporte | 1.89 s |
| **Total** | ~4.3 min |

Ahorro real medido: **4.9 %** (limpio) y **14.1 %** (inglés) frente al original.

---

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

Los tests **no requieren red**: cubren validación, preprocesamiento, extracción,
tokens, costeo, reporte, ingesta y un test integral con `optimizar_tokens=False`.

---

## Documentación técnica

Ver [docs/documento_tecnico.md](docs/documento_tecnico.md) para el detalle de la
arquitectura, decisiones de diseño, modelo económico, contrato de datos,
heurísticas y trazabilidad con los criterios de aceptación.

---

## Solución de problemas

| Problema | Solución |
|---|---|
| `ColumnValidationError: Faltan columnas obligatorias` | El `.xlsx` debe incluir `paciente_id` (o `id_paciente`) y `mensaje_texto` |
| `PermissionError` al sobrescribir un `.xlsx` | El archivo está abierto en Excel; ciérralo y reintenta |
| La traducción cae a `deep_translator` | No hay `models/*/model.bin`; ejecuta `python scripts/setup_ctranslate2_model.py` |
| `pip` no encuentra wheels en Python 3.11 | Usa Python 3.12+ (los wheels cp314/cp312 están disponibles) |
| Error `faker` no instalado | `pip install faker` (incluido en `requirements.txt`) |
| Quieres borrar los outputs | `Remove-Item out\*` (o `rm -rf out`) |

---

## Licencia

Proyecto interno de la historia de usuario HU-015. Sin dependencias externas de
pago; la traducción local elimina la dependencia de red y de servicios de pago.
