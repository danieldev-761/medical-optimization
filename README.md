# Medical Opt · HU-015

Pipeline por etapas de alto rendimiento para procesar solicitudes de citas médicas desde archivos `.xlsx` (archivo único o carpeta), evaluar la optimización de tokens en español vs. inglés y producir un Excel estructurado más un dashboard analítico interactivo en tiempo real con KPIs, costos y proyecciones.

Diseñado para **rapidez de ejecución masiva**: inferencia local CTranslate2 con caché Redis, paralelización multinúcleo en CPU (`ProcessPoolExecutor`) bypass de GIL, tokenización C/Rust con `tiktoken`, y procesamiento 100% en memoria RAM sin archivos intermedios en disco.

---

## 🛠️ Stack Tecnológico

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Procesamiento de Datos | `pandas`, `openpyxl`, `numpy` |
| Concurrencia & Multiproceso | `ProcessPoolExecutor` (Paralelización CPU en 12 núcleos), `ThreadPoolExecutor` (I/O) |
| Tokenización | `tiktoken` (encoding `o200k_base` vectorizado en Rust/C) |
| Traducción & Caché | `ctranslate2` (Inferencia C++ local en CPU) + **Redis 7** (`MGET`/`MSET` con compresión semántica) |
| API & Servidor | `FastAPI`, `uvicorn`, Server-Sent Events (SSE en vivo) |
| Frontend | HTML5 / CSS3 Vanilla Glassmorphism + Chart.js (Dashboard interactivo sin frameworks) |
| Suite de Pruebas | `pytest` (25 tests unitarios e integrales) |
| Contenedores | Docker & Docker Compose (`medical_api` + `medical_redis`) |

---

## 🔥 Características de Alto Rendimiento

- **Paralelismo Multinúcleo CPU (`ProcessPoolExecutor`)**: Distribución automática del preprocesamiento y extracción Regex de intenciones/especialidades a través de todos los procesadores lógicos de la máquina (salto total del GIL de Python).
- **Traducción Ultra-Rápida con Redis**: Deduplicación por clave semántica limpia (`list(dict.fromkeys(cleaned))`). Para datasets de 10,000 o 50,000 registros, el pipeline comprime las frases y traduce **únicamente 8 oraciones únicas**, reduciendo la latencia de traducción a **`0.008s - 0.010s`** (99.98% de ahorro en cómputo).
- **Tokenización Vectorizada C/Rust (`tiktoken`)**: Conteo masivo de tokens en C/Rust en una sola llamada batch directamente sobre la memoria RAM.
- **Flujo 100% en Memoria**: Eliminación total de la escritura física de CSVs intermedios en disco durante el pipeline síncrono.
- **Validación de Columnas y Alias**: Soporte automático para alias como `id_paciente -> paciente_id` y `especialidad_medica -> especialidad`.
- **Deduplicación por Paciente**: Preservación estricta de ocurrencias múltiples por paciente (`subset=['paciente_id', '_clean_key']`).
- **Dashboard Web Interactivo**: Monitoreo en vivo etapa por etapa vía SSE (`/api/analyze/stream`), KPIs de ahorro, comparativa de variantes (Original, Limpio, Inglés) y gráficos con Chart.js.

---

## ⚡ Rendimiento y Benchmarks

Procesamiento completo de **10,000 y 50,000 registros** (`ctranslate2` + `Redis` + `ProcessPoolExecutor`):

| Etapa | Tiempo Medido | Descripción / Optimización |
|---|:---:|---|
| **Ingesta** | ~1.58 s | Lectura e inspección del Excel |
| **Validación** | 0.003 s | Normalización de alias y esquema obligatorio |
| **Preprocesamiento** | **0.89 s** | Limpieza semántica paralelizada en 12 núcleos CPU |
| **Extracción Regex** | **0.45 s** | Extracción de intenciones y especialidades paralelizada |
| **Tokenización (3 variantes)** | ~1.60 s | `tiktoken` batch vectorizado C/Rust |
| **Traducción (Redis / C++)** | **0.009 s** | Compresión semántica (solo 8 frases únicas traducidas) |
| **Reporte Excel** | ~1.90 s | Generación del contrato Excel final |
| **TOTAL PIPELINE** | **~4.9 - 7.3 s** | **Reducción desde los 4 minutos iniciales** |

---

## 🚀 Instalación y Despliegue

### Opción A: Con Docker Compose (Recomendado)

El sistema incluye Docker Compose preconfigurado con el servicio de API FastAPI y el servidor de Caché Redis.

```bash
# Construir e iniciar contenedores en segundo plano
docker compose up -d --build

# Verificar contenedores corriendo
docker compose ps
```

Accede al Dashboard en tu navegador: **`http://localhost:8000`**

---

### Opción B: Ejecución Local

```bash
# Crear y activar entorno virtual
python -m venv .venv
source .venv/bin/activate  # En Linux/macOS
# .venv\Scripts\activate   # En Windows

# Instalar dependencias
pip install -r requirements.txt

# Iniciar servidor Redis (requerido para caché)
redis-server --daemonize yes

# Iniciar servidor web
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 💻 Uso

### 1. Interfaz Web (Dashboard)
1. Abre `http://localhost:8000` en tu navegador.
2. Sube un archivo `.xlsx` (ejemplo: `sample/citas_medicas_solicitudes.xlsx`).
3. Elige el motor de traducción (`ctranslate2` por defecto).
4. Visualiza el avance etapa por etapa en tiempo real y descarga el Excel final optimizado.

### 2. Línea de Comandos (CLI)

```bash
# Ejecutar pipeline completo sobre un archivo
python run.py sample/citas_medicas_solicitudes.xlsx --engine ctranslate2

# Ejecutar sin optimización de tokens
python run.py sample/citas_medicas_solicitudes.xlsx --no-optimize
```

---

## 🧪 Ejecución de Tests

La suite incluye 25 pruebas unitarias e integrales (validación, preprocesamiento, extracción regex, caché Redis, tokenización y endpoints API):

```bash
# Ejecutar tests en el contenedor Docker
docker exec -e PYTHONPATH=/app medical_api pytest tests/

# O localmente
pytest tests/
```

---

## 📄 Contrato del Excel de Salida (`Resultados`)

Hoja única ordenada según el contrato requerido:

| # | Columna | Descripción |
|---|---|---|
| 1 | `paciente_id` | Identificador único del paciente |
| 2 | `paciente` | Nombre completo del paciente |
| 3 | `mensaje_texto` | Mensaje original recibido |
| 4 | `mensaje_limpio` | Mensaje procesado y optimizado en español |
| 5 | `mensaje_ingles` | Traducción al inglés de la versión limpia |
| 6 | `accion` | Intención detectada (`reprogramar`, `cancelar`, `confirmar`) |
| 7 | `especialidad` | Especialidad médica identificada |
| 8 | `fecha_solicitada` | Referencia o fecha detectada |
| 9 | `preferencia_horario` | Turno u horario de preferencia |
| 10 | `tokens_original` | Tokens consumidos por el mensaje original |
| 11 | `tokens_limpio` | Tokens consumidos por la versión limpia |
| 12 | `tokens_ingles` | Tokens consumidos por la versión traducida |
| 13 | `costo_estimado_original` | Costo en USD de la variante original |
| 14 | `costo_estimado_limpio` | Costo en USD de la variante limpia |
| 15 | `costo_estimado_ingles` | Costo en USD de la variante traducida |
