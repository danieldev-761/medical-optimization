# Documento Técnico — HU-015 · Medical Opt

> Pipeline por etapas para el procesamiento de solicitudes de citas médicas,
> optimización de tokens (español vs. inglés) y análisis económico.

**Versión del documento:** 1.0  
**Historia de usuario:** HU-015  
**Fecha:** 2026-07-30

---

## 1. Contexto y objetivo

La solución procesa solicitudes de citas médicas provenientes de archivos Excel
(`.xlsx`), individuales o agrupados en una carpeta. El objetivo técnico principal
es **reducir el tiempo total de procesamiento** sobre cargas masivas y, de forma
complementaria, evaluar el **ahorro económico** al optimizar los mensajes antes de
enviarlos a un LLM.

La estrategia de rendimiento se sostiene en cuatro principios:

1. Reducir I/O pesado (conversión temprana a CSV).
2. Evitar trabajo inútil (descarte temprano de filas vacías y deduplicación).
3. Concentrar el análisis en una sola columna (`mensaje_texto`).
4. Aplicar concurrencia únicamente donde aporta (I/O-bound).

---

## 2. Decisiones funcionales cerradas

| Decisión | Valor |
|---|---|
| Entrada | `.xlsx` único **o** carpeta con múltiples `.xlsx` (consolidación) |
| Formato intermedio | CSV (reduce sobrecarga frente a trabajar sobre `.xlsx`) |
| Columna analizada | Solo `mensaje_texto`; el resto se preserva como trazabilidad |
| Limpieza | Filas vacías, nulas o sin valor semántico descartadas antes de las etapas costosas |
| Acciones válidas | `confirmar`, `cancelar`, `reprogramar` |
| Campos opcionales | `fecha_solicitada` y `preferencia_horario` pueden quedar vacíos |
| Salida Excel | Una sola hoja |
| Tarifa | 2.50 USD por millón de tokens |
| Proyección | 15,000 mensajes por día |

---

## 3. Modo `optimizar_tokens`

### 3.1 `optimizar_tokens = False`

Solo se ejecuta validación básica de integridad y se procesa el **mensaje
original en español**. No hay arbitraje de costo, comparación entre variantes ni
limpieza orientada a reducción de tokens. Las columnas `tokens_ingles` y
`costo_estimado_ingles` quedan **nulas** y se excluyen del análisis y proyección.

### 3.2 `optimizar_tokens = True`

Se ejecuta una etapa previa de evaluación de costo y tokenización sobre **tres
variantes** del mismo `mensaje_texto`:

| Variante | Descripción |
|---|---|
| `original` | Texto tal como llega en la fuente |
| `limpio` | Resultado de la limpieza semántica |
| `ingles` | Traducción al inglés de la versión **limpia** |

La traducción ocurre **siempre** sobre `mensaje_texto` limpio, nunca sobre otras
columnas. Para cada variante se registran tokens y costo estimado en el Excel
final y en el dashboard.

---

## 4. Arquitectura por capas

```
┌──────────────────────────────────────────────────────────────┐
│                        Presentación                          │
│   FastAPI (dashboard + API) · Excel final · agregados JSON   │
├──────────────────────────────────────────────────────────────┤
│                         Análisis                             │
│   Costeo (2.50 USD/M) · Proyección hipotética                │
├──────────────────────────────────────────────────────────────┤
│                 Análisis lingüístico                         │
│   Tokenización (o200k_base) · Traducción (ct2 / dt)          │
├──────────────────────────────────────────────────────────────┤
│                      Extracción                              │
│   Heurísticas/regex: accion, especialidad, fecha, horario    │
├──────────────────────────────────────────────────────────────┤
│                    Preprocesamiento                          │
│   Filtrado · limpieza semántica · deduplicación              │
├──────────────────────────────────────────────────────────────┤
│                    Normalización                             │
│   .xlsx → CSV · estandarización de columnas (aliases)        │
├──────────────────────────────────────────────────────────────┤
│                        Ingesta                               │
│   Archivo único o carpeta · consolidación concurrente        │
└──────────────────────────────────────────────────────────────┘
```

| Capa | Módulo | Responsabilidad |
|---|---|---|
| Ingesta | `pipeline/ingest.py` | Descubrir `.xlsx` (único o carpeta), lectura concurrente, consolidación |
| Normalización | `pipeline/ingest.py`, `validate.py` | CSV intermedio, normalización de nombres y aliases |
| Preprocesamiento | `pipeline/preprocess.py` | Validar filas, filtrar vacíos, limpiar ruido, deduplicar |
| Extracción | `pipeline/extract.py` | Detectar `accion`, `especialidad`, `fecha_solicitada`, `preferencia_horario` |
| Tokenización | `pipeline/tokens.py` | `tokens_original`, `tokens_limpio`, `tokens_ingles` con `o200k_base` |
| Traducción | `pipeline/translate.py` | ES→EN del texto limpio (ctranslate2 / deep_translator) |
| Costeo | `pipeline/cost.py` | Costo por variante + proyección hipotética |
| Presentación | `pipeline/report.py`, `app/main.py`, `static/` | Excel, agregados JSON, dashboard y API |

---

## 5. Pipeline detallada

La orquestación vive en `app/pipeline/pipeline.py` (`run_pipeline`). Cada etapa
está instrumentada con el context manager `stage_timer` y reporta progreso al
`ProgressReporter`.

| # | Etapa | Entrada | Salida | Detalle |
|---|---|---|---|---|
| 1 | **Ingesta** | ruta (archivo o carpeta) | `DataFrame` consolidado | `ThreadPoolExecutor(4)` para lectura de archivos; inserta columna `archivo_origen` para trazabilidad |
| 2 | **Validación** | DataFrame | DataFrame con columnas normalizadas | Exige `paciente_id` y `mensaje_texto`; renombra aliases (`id_paciente`); guardia contra columnas duplicadas |
| 3 | **CSV intermedio** | DataFrame | `out/intermediate.csv` | Persiste el consolidado como CSV para trabajo posterior más barato |
| 4 | **Preprocesamiento** | DataFrame | DataFrame limpio + stats | Filtrado de vacíos, `mensaje_limpio`, deduplicación por clave normalizada |
| 5 | **Extracción** | DataFrame | `accion`, `especialidad`, `fecha_solicitada`, `preferencia_horario` | Heurísticas por regex/diccionarios (sin LLM) |
| 6 | **Tokens original** | `mensaje_texto` | `tokens_original` | Batches de 500; `tiktoken` `o200k_base` |
| 7 | **Tokens limpio** | `mensaje_limpio` | `tokens_limpio` | Idem |
| 8 | **Traducción** *(solo si optimize)* | `mensaje_limpio` (dedup global) | `mensaje_ingles` | ctranslate2 por lotes con fallback deep_translator; caché por texto; progreso por lote |
| 9 | **Tokens inglés** *(solo si optimize)* | `mensaje_ingles` | `tokens_ingles` | Idem; si `optimize=False`, queda `pd.NA` |
| 10 | **Costeo** | tokens | 3 columnas `costo_estimado_*` | `costo = tokens / 1_000_000 × 2.50` |
| 11 | **Reporte** | DataFrame procesado | `resultados.xlsx` + `agregados.json` + `metrics.json` | Ensambla el contrato exacto de columnas y agrega |

Si en cualquier etapa el volumen queda vacío se lanza un error controlado
(`ValueError`) que el API traduce a `HTTP 500` con mensaje legible.

---

## 6. Contrato de datos

### 6.1 Entrada

**Columnas obligatorias** (tras normalización):

| Columna canónica | Aliases aceptados | Tipo esperado |
|---|---|---|
| `paciente_id` | `id_paciente` | string |
| `mensaje_texto` | `mensaje` | string (puede venir vacío/nulo) |

**Columnas opcionales** preservadas como trazabilidad: `paciente`, `ciudad`,
`especialidad_medica`, `fecha_solicitada`, `accion`, `especialidad`,
`preferencia_horario`, `archivo_origen` (añadida por la pipeline).

Normalización aplicada en `validate.py`:
- Nombres de columna en minúsculas y sin espacios (`str.strip().lower()`).
- Renombrado de aliases (`COLUMN_ALIASES`).
- Eliminación de columnas duplicadas tras la renombrada (formatos mixtos).

### 6.2 Salida Excel

Una sola hoja (`Resultados`) con el orden exacto definido en `OUTPUT_COLUMNS`
(véase la sección 7 del README). Los campos `fecha_solicitada` y
`preferencia_horario` quedan vacíos cuando no se mencionan explícitamente.

### 6.3 Representación de vacíos

- Entrada: `""`, `NaN`, espacios, o texto sin valor → descartadas en preprocesamiento.
- Salida: celdas vacías en Excel; `null` en JSON.
- `tokens_ingles` en `optimizar_tokens=False`: `pd.NA` → celda vacía.

---

## 7. Preprocesamiento y limpieza semántica

Implementado en `preprocess.py`. **Conservadora**: elimina ruido sin perder
intención, especialidad ni preferencias temporales.

Operaciones:
1. Normalización de saltos de línea y espacios múltiples.
2. Corte de colas no operativas en conectores de posdata
   (`att.`, `atte.`, `saludos a`, `quedo a su disposicion`, …).
3. Remoción de cortesías y frases accesorias
   (`por favor`, `gracias`, `buenos días`, `hola`, `saludos`, `urgente`, …).
4. Filtrado de caracteres residuales no alfanuméricos.
5. Descarte si el mensaje queda vacío o sin valor semántico (`len < 3` sin letras).

**Deduplicación**: clave = `mensaje_limpio` normalizado a ASCII y minúsculas.
Se conserva la primera ocurrencia por clave.

**Batching**: `preprocess.iter_batches` divide el DataFrame en lotes de tamaño
`batch_size` (500 por defecto) para limpieza/tokenización.

---

## 8. Extracción heurística

Implementado en `extract.py`. Sin llamadas externas y con precedencia explícita.

### 8.1 `accion`

Patrones por diccionario con **precedencia**: `cancelar` → `reprogramar` →
`confirmar`. La precedencia evita que mensajes ambiguos
(«confirmar si es posible postergar») se clasifiquen como confirmación.

| Acción | Términos reconocidos (muestra) |
|---|---|
| `cancelar` | cancelar, cancelación, anular, «no podré asistir», «no asistiré», «dar de baja» |
| `reprogramar` | reprogramar, reagendar, cambiar fecha/horario, modificar fecha, posponer, postergar, aplazar, adelantar turno/cita |
| `confirmar` | confirmar, confirmación, reafirmar, «sí, quiero mantener» |

### 8.2 `especialidad`

Diccionario de 20+ especialidades con variantes (ej. `cardio*`, `dermato*`,
`oftalmo*`, `neuro*`, `traumat*`, `dentista`, `medicina general`, `vacunación`,
`laboratorio`/`análisis`/`exámenes`).

### 8.3 `fecha_solicitada`

Patrones con orden de especificidad decreciente: fechas con mes explícito
(«15 de mayo»), `YYYY-MM-DD`, `DD/MM`, «día N», «pasado mañana», «próxima
semana», «próximo mes», «la siguiente semana», «este {día}», día de la semana,
«mañana».

### 8.4 `preferencia_horario`

`(por|en|para|durante) la mañana/tarde/noche`, «horario/turno de la
mañana/tarde/noche», «primeras horas del día», «mediodía», «a las H(:MM) (am/pm)»,
«HH:MM am/pm».

Todos los textos se normalizan a ASCII y minúsculas antes del matching, de modo
que «próxima» = `proxima`.

---

## 9. Tokenización

Implementado en `tokens.py` con `tiktoken`, encoding **`o200k_base`** (el mismo
que usa la familia de modelos modernos de OpenAI).

- `count_tokens(text) → int`; texto vacío → `0`.
- `count_tokens_batch(texts) → list[int]`: una sola llamada al encoder por batch
  (mucho más rápida que llamadas individuales).

La tokenización es **CPU-bound**; por eso se ejecuta en batches secuenciales y se
deja documentado en el plan que, si el profiling la revelara como cuello de
botella real, se evaluaría `ProcessPoolExecutor`.

---

## 10. Traducción

Implementado en `translate.py`. Dos motores con fallback automático:

### 10.1 `ctranslate2` (local, recomendado)

- Modelo: `Helsinki-NLP/opus-mt-es-en` convertido a formato CTranslate2 (int8).
- Setup: `scripts/setup_ctranslate2_model.py` (usa `torch` CPU y `transformers`
  solo durante la conversión; el runtime solo necesita `ctranslate2` +
  `transformers` + `sentencepiece` + `sacremoses`).
- Tokenización para CT2: `convert_ids_to_tokens(tokenizer.encode(text))` —
  crucial para decodificar correctamente (evita el problema de salida repetitiva
  que se observó al usar `tokenizer.tokenize`).
- Decodificación: `convert_tokens_to_string(hypotheses[0])`.
- `beam_size=1` (greedy) por velocidad/calidad en este dominio.

### 10.2 `deep_translator` (fallback)

- Google Translate gratuito vía red, `GoogleTranslator(source="es",
  target="en").translate_batch(texts)` (un request por lote).
- I/O-bound → se ejecuta con `ThreadPoolExecutor(max_workers=8)`.

### 10.3 Selección de motor (`auto`)

`_ctranslate2_available()` verifica la existencia de `models/*/model.bin`:

- Modelo presente → `ctranslate2`.
- Modelo ausente o fallo de carga → `deep_translator`.

El motor efectivamente usado queda registrado en `_meta.motor_traduccion` y en el
badge del dashboard.

### 10.4 Caché y deduplicación

`_translate_with_cache`:
1. Deduplica los textos limpios (`dict.fromkeys`).
2. Traduce solo los únicos, repartidos en chunks de 100 con 8 workers.
3. Reporta progreso por lote (`on_batch`) al `ProgressReporter`.
4. Reconstruye la columna `mensaje_ingles` mapeando por texto limpio.

---

## 11. Modelo económico

### 11.1 Fórmula base

```
costo_estimado = (tokens / 1_000_000) × 2.50 USD
```

### 11.2 Bloque 1 — Proceso real

Costo total observado en el lote realmente procesado, a partir de las columnas
exportadas:

- `costo_original = Σ tokens_original / 1e6 × 2.5`
- `costo_limpio   = Σ tokens_limpio   / 1e6 × 2.5`
- `costo_ingles   = Σ tokens_ingles   / 1e6 × 2.5`
- `ahorro_limpio  = costo_original − costo_limpio` (+ %)
- `ahorro_ingles  = costo_original − costo_ingles` (+ %)

### 11.3 Bloque 2 — Volumen hipotético

Proyección para **15,000 mensajes/día** a partir del **promedio real de tokens
por mensaje** de cada variante:

```
mensajes_periodo   = 15_000 × días
tokens_periodo     = promedio_tokens_por_mensaje × mensajes_periodo
costo_periodo      = tokens_periodo / 1e6 × 2.5
```

| Periodo | Días |
|---|---|
| Diario | 1 |
| Mensual | 30 |
| Trimestral | 90 |
| Anual | 365 |

El promedio por variante solo se calcula sobre filas con valor (en
`optimizar_tokens=False` se excluye la variante inglés).

### 11.4 Estructura de `agregados.json`

```jsonc
{
  "n_procesadas": 8980,
  "totales": { "tokens_original": ..., "tokens_limpio": ...,
               "tokens_ingles": ..., "costo_original": ..., ... },
  "ahorro": { "limpio_absoluto": ..., "limpio_pct": ...,
              "ingles_absoluto": ..., "ingles_pct": ... },
  "promedio_tokens_por_mensaje": { "original": ..., "limpio": ..., "ingles": ... },
  "distribucion_acciones": { "reprogramar": ..., "cancelar": ... },
  "distribucion_especialidades": { "cardiologia": ..., ... },
  "proyeccion": { "original": { "diario": {...}, "mensual": {...}, ... },
                  "limpio": {...}, "ingles": {...},
                  "_meta": { "mensajes_por_dia": 15000,
                             "tarifa_usd_por_millon": 2.5 } },
  "preprocesamiento": { "filas_leidas": ..., "filas_descartadas_vacio": ...,
                        "duplicados_eliminados": ..., "filas_validas": ... },
  "_meta": { "motor_traduccion": ..., "optimizar_tokens": ...,
             "tarifa_usd_por_millon": 2.5, "mensajes_por_dia_proyeccion": 15000,
             "tiempos_seg": { "ingesta": ..., "traduccion": ..., ... } }
}
```

---

## 12. Progreso en tiempo real (SSE)

### 12.1 `ProgressReporter` (`progress.py`)

Modela el avance como pesos por etapa:

```
ingesta .06 · validacion .02 · csv .02 · preprocesamiento .05 · extraccion .06
tokens_original .07 · tokens_limpio .05 · traduccion .50 · tokens_ingles .05
costeo .02 · reporte .10
```

- En `optimizar_tokens=False` se excluyen `traduccion` y `tokens_ingles` y los
  pesos se renormalizan por el total restante.
- `stage(name)` notifica el inicio (progreso acumulado) y fija la base de la etapa.
- `sub(fraction)` reporta avance parcial dentro de la etapa (traducción por lote).
- `end(name)` acumula el peso completado.
- La emisión es **monotónica** (no retrocede), garantizada porque el sub-progreso
  se calcula sobre la base fijada al iniciar la etapa, no sobre el acumulado
  actual.

### 12.2 Endpoint `POST /api/analyze/stream`

- Recibe el archivo (multipart) y query params (`optimize_tokens`, `engine`, `batch_size`).
- Guarda el archivo en un directorio temporal único por corrida.
- Ejecuta `run_pipeline(..., progress=listener)` en un hilo worker.
- Emite eventos SSE por una cola:
  - `{"type":"stage","etapa":..., "progreso": <0-100>}`
  - `{"type":"done","data":{agregados}}`
  - `{"type":"error","detail":"..."}`
- Limpia el directorio temporal en `finally`.

### 12.3 Cliente (frontend)

`app.js` usa `fetch` + `ReadableStream` (no `EventSource`, que solo soporta GET),
decodifica los eventos SSE y actualiza la barra con `label` + `%`. Al recibir
`done`, renderiza el análisis y oculta la barra.

---

## 13. API (FastAPI)

| Método | Ruta | Comportamiento |
|---|---|---|
| `GET` | `/` | Sirve `static/index.html` |
| `GET` | `/api/results` | Lee `out/agregados.json`; `404` si no existe |
| `POST` | `/api/analyze` | Procesa y responde JSON al finalizar (sin streaming) |
| `POST` | `/api/analyze/stream` | Procesa y emite SSE con progreso |
| `GET` | `/api/download` | Descarga `out/resultados.xlsx`; `404` si no existe |

Errores: `400` (archivo no `.xlsx`), `404` (sin resultados/excel), `500`
(fallos internos de la pipeline, con `detail` legible).

---

## 14. Frontend / Dashboard

- **Sin framework**: HTML + CSS + JS vanilla y Chart.js (CDN).
- **Flujo correcto**: no hay datos mockeados ni precarga; la sección "Procesar
  archivo" es lo primero. El bloque `<section id="analysis">` está oculto
  (`hidden`) hasta que llega el evento `done`.
- **Vistas**:
  - *Análisis real*: KPIs de volumen, tarjetas por variante (tokens/costo/promedio),
    ahorro absoluto y %, comparativas de tokens/costo, ahorro, distribución de
    acciones y tabla de profiling.
  - *Proyección hipotética*: tarjetas por periodo (diario/mensual/trimestral/anual)
    y gráficas de costo y tokens por variante.
- **Estado del motor**: badge con el motor de traducción efectivo
  (`ctranslate2` / `deep_translator`).
- **Descarga**: botón de Excel solo visible tras el análisis.

---

## 15. Rendimiento y concurrencia

| Parámetro | Valor por defecto | Dónde |
|---|---|---|
| `batch_size` | 500 | `config.py` / `Settings` |
| `max_workers_ingest` | 4 | `ingest.py` (lectura de archivos) |
| `max_workers_translate` | 8 | `pipeline.py` (traducción) |
| Chunk de traducción | 100 textos | `_translate_with_cache` |
| Caché | por texto limpio | `_translate_with_cache` |
| Timeout/retries externos | 30 s / 2 | `config.py` (reserva para servicios) |

### 15.1 Medición de referencia

Carga: `sample/citas_medicas_solicitudes.xlsx` (10,000 filas, 10 % vacías).
Motor: `ctranslate2` local. Hardware: CPU.

| Etapa | Tiempo |
|---|---|
| Ingesta | 1.09 s |
| Validación | 0.005 s |
| CSV intermedio | 0.05 s |
| Preprocesamiento | 0.95 s |
| Extracción | 2.23 s |
| Tokens original | 0.84 s |
| Tokens limpio | 0.41 s |
| Traducción (8,980 mensajes) | 246.8 s |
| Tokens inglés | 0.62 s |
| Costeo | 0.03 s |
| Reporte | 1.89 s |

Resultados del lote: 8,980 válidos · tokens 275,769 → 262,345 → 236,921 ·
ahorro **4.9 %** (limpio) y **14.1 %** (inglés).

**Comparación de motores** (784 mensajes):

| Motor | Tiempo | Nota |
|---|---|---|
| `deep_translator` (Google) | ~54 s | Depende de red; sujeto a rate limits |
| `ctranslate2` (local) | ~14.8 s | Sin red, ~3.6× más rápido, sin límites |

---

## 16. Estructura de código

```
app/
  main.py                # FastAPI (dashboard + API + SSE)
  config.py              # constantes y Settings
  static/                # index.html, style.css, app.js
  pipeline/
    ingest.py            # descubrimiento, lectura concurrente, consolidación, CSV
    validate.py          # columnas obligatorias y aliases
    preprocess.py        # filtrado, limpieza, dedup, batches
    extract.py           # heurísticas de extracción
    tokens.py            # tiktoken o200k_base
    translate.py         # ctranslate2 + deep_translator + selección auto
    cost.py              # costeo y proyección
    report.py            # Excel y agregados
    progress.py          # reporter de progreso SSE
    metrics.py           # stage_timer / Metrics
    pipeline.py          # orquestador run_pipeline
scripts/
  generate_citas.py          # generador oficial de datos (Faker)
  setup_ctranslate2_model.py # conversión del modelo local
tests/
  test_pipeline.py           # unitarios por etapa
  test_end_to_end.py         # integral sin red
run.py                    # CLI
```

---

## 17. Instrumentación y profiling

- `Metrics` (`metrics.py`) acumula duraciones por etapa con `stage_timer`.
- Cada corrida escribe `out/metrics.json`:
  ```json
  { "etapas_seg": { "ingesta": 1.09, "traduccion": 246.8, ... } }
  ```
- El dashboard muestra la tabla de profiling al procesar vía API.
- Sirve para detectar cuellos de botella reales y decidir ajustes de
  `batch_size`/workers sin optimización prematura.

---

## 18. Tests

`tests/test_pipeline.py` — unitarios (sin red):
- Validación: columnas faltantes lanzan `ColumnValidationError`; alias `id_paciente`.
- Preprocesamiento: limpieza de cortesías, preservación de intención, filtrado, dedup.
- Extracción: acciones (incluido vocabulario formal), especialidad, fecha/horario.
- Tokens: conteo y batch consistente.
- Costeo: fórmula y proyección.
- Reporte: contrato exacto de columnas y agregados.
- Ingesta: consolidación con `archivo_origen`, descubrimiento de carpeta,
  extensión inválida.

`tests/test_end_to_end.py` — integral con `optimizar_tokens=False` (sin
traducción, sin red): estadísticas esperadas, Excel legible, proyección sin
variante inglés.

---

## 19. Trazabilidad con criterios de aceptación

| Criterio | Cumplimiento |
|---|---|
| C1. Carga flexible y validación | `ingest.py` acepta archivo único o carpeta; `validate.py` valida `paciente_id`/`mensaje_texto` antes del análisis; CSV intermedio en la etapa 3 |
| C2. Limpieza y reducción de volumen | `preprocess.py` descarta vacíos/nulos antes de tokenizar/traducir; limpieza conservadora solo sobre `mensaje_texto`; dedup |
| C3. Modo `optimizar_tokens` | `pipeline.py` ramifica las variantes; traducción siempre sobre texto limpio; `False` → solo original + `tokens_ingles` nulo |
| C4. Salida estructurada | `report.py` genera Excel de 1 hoja con `OUTPUT_COLUMNS` exacto; campos opcionales vacíos; tarifa 2.50 USD/M |
| C5. Dashboard analítico | KPIs, gráficas comparativas, proyección 15k/día con la misma tarifa, distinción real vs. hipotético |
| C6. Rendimiento | Batches, concurrencia solo I/O, instrumentación por etapa, caché de traducción |

---

## 20. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación implementada |
|---|---|---|
| Traducción por fila lenta | Alto | Batching, `ThreadPoolExecutor`, caché, dedup, progreso por lote |
| Sobrecarga sobre `.xlsx` | Alto | Conversión temprana a CSV |
| Limpieza agresiva que pierde información | Alto | Heurísticas conservadoras; solo `mensaje_texto`; validación de campos extraídos |
| Saturación de servicios externos | Medio | Motor local ctranslate2 como primera opción; fallback acotado; workers limitados |
| Tokenización CPU-bound | Medio | Profiling por etapa; batched encoding; `ProcessPoolExecutor` documentado como paso siguiente si el profiling lo justifica |

---

## 21. Pasos siguientes sugeridos

1. Evaluar `ProcessPoolExecutor` para tokenización si el profiling con lotes
   grandes (>50k filas) lo justifica.
2. Convertir y versionar automáticamente el modelo local en CI (o caché de modelo
   compartida) para eliminar el paso manual de setup.
3. Soporte de tipos de archivo adicionales (`.csv` de origen, `.xls`).
4. Exportar las gráficas del dashboard (PNG/SVG) para reportes.
5. Pruebas de carga y ajuste de `max_workers_translate` según hardware y rate
   limits del proveedor si se usa deep_translator.
