# Medical Opt · HU-015

Pipeline por etapas de alto rendimiento para procesar solicitudes de citas médicas desde archivos `.xlsx` (archivo único o carpeta), evaluar la optimización de tokens en español vs. inglés y producir un Excel estructurado más un dashboard analítico interactivo en tiempo real con KPIs, costos y proyecciones.

Diseñado para **rapidez de ejecución masiva**: inferencia local CTranslate2 con caché Redis, paralelización multinúcleo en CPU (`ProcessPoolExecutor`) con bypass del GIL, tokenización C/Rust con `tiktoken`, y procesamiento 100% en memoria RAM sin archivos intermedios en disco.

---

## 🛠️ Stack Tecnológico

| Componente | Tecnología |
|---|---|
| Lenguaje | Python 3.11+ |
| Procesamiento de Datos | `pandas`, `openpyxl`, `numpy` |
| I/O Excel | `python-calamine` (lectura) + `xlsxwriter` (escritura) con fallback a `openpyxl` |
| Concurrencia & Multiproceso | `ProcessPoolExecutor` (paralelización CPU en 12 núcleos), `ThreadPoolExecutor` (I/O) |
| Tokenización | `tiktoken` (encoding `o200k_base` en Rust/C, bucle plano + pool de procesos) |
| Traducción & Caché | `ctranslate2` (inferencia C++ local en CPU con `opus-mt-es-en`) + **Redis 7** (`MGET`/`MSET` con compresión semántica) |
| API & Servidor | `FastAPI`, `uvicorn`, Server-Sent Events (SSE en vivo) |
| Frontend | HTML5 / CSS3 Vanilla Glassmorphism + Chart.js (Dashboard interactivo sin frameworks) |
| Suite de Pruebas | `pytest` (25 tests unitarios e integrales) |
| Contenedores | Docker & Docker Compose (`medical_api` + `medical_redis`) + `docker-compose.override.yml` (dev con auto-reload) |

---

## 🔥 Características de Alto Rendimiento

- **Paralelismo Multinúcleo CPU (`ProcessPoolExecutor`)**: bypass total del GIL. La limpieza semántica y la extracción Regex de intenciones/especialidades se ejecutan en **un único pase paralelo**; la tokenización de las 3 variantes también se paraleliza por procesos.
- **Ingesta Ultra-Rápida con `python-calamine`**: lectura del `.xlsx` en Rust, ~6x más rápida que `openpyxl` (con fallback automático).
- **Traducción Ultra-Rápida con Redis**: deduplicación por clave semántica limpia (`list(dict.fromkeys(cleaned))`). Para datasets de 10,000 o 50,000 registros el pipeline comprime las frases y traduce **únicamente ~8 oraciones únicas**, reduciendo la latencia a ~`0.008s - 0.025s` (99.98% de ahorro en cómputo) usando el modelo local `opus-mt-es-en`.
- **Tokenización sin overhead**: se evita `encode_batch` (su `ThreadPoolExecutor` interno agrega overhead por item sin paralelizar por el GIL) y se usa un bucle plano de `encode` + `ProcessPoolExecutor`, pasando de ~5.6 s a ~0.8 s en 50k registros.
- **Reporte Excel optimizado**: una sola escritura con `xlsxwriter` (más rápido y liviano que `openpyxl`) y la copia `resultados.xlsx` vía `shutil.copy2` (~0.001 s). La etapa de reporte pasa de ~19.8 s a ~6.9 s.
- **Extracción selectiva**: los campos que el input ya provee completos (`especialidad`, `fecha_solicitada`) se preservan tal cual (el input gana) y no se extraen; la extracción solo rellena huecos.
- **Flujo 100% en Memoria**: eliminación total de la escritura física de CSVs intermedios en disco durante el pipeline síncrono.
- **Validación de Columnas y Alias**: soporte automático para alias como `id_paciente -> paciente_id` y `especialidad_medica -> especialidad`.
- **Deduplicación por Paciente**: preservación estricta de ocurrencias múltiples por paciente (`subset=['paciente_id', '_clean_key']`).
- **Métricas en vivo antes del Excel**: el streaming SSE emite las métricas en cuanto termina el análisis (antes de escribir el Excel, la etapa más lenta); el botón de descarga aparece **bloqueado** y se **desbloquea** cuando el Excel queda listo.
- **Dashboard Web Interactivo**: monitoreo en vivo etapa por etapa vía SSE (`/api/analyze/stream`), KPIs de ahorro, comparativa de variantes (Original, Limpio, Inglés), gráficos Chart.js y profiling por etapa.

---

## ⚡ Rendimiento y Benchmarks

Procesamiento completo de **10,000 y 50,000 registros** medido en contenedor Docker (12 núcleos, `ctranslate2` + Redis + `ProcessPoolExecutor`):

| Etapa | 10k | 50k | Optimización |
|---|:---:|:---:|---|
| **Ingesta** | 0.11 s | 0.83 s | Lectura con `python-calamine` |
| **Validación** | 0.002 s | 0.004 s | Normalización de alias y esquema obligatorio |
| **Preprocesamiento + Extracción** | 0.35 s | 1.63 s | Limpieza + regex fusionadas en un solo pase paralelo |
| **Tokenización (3 variantes)** | 0.42 s | 0.80 s | Bucle plano `tiktoken` + pool de procesos |
| **Traducción (Redis / C++)** | 0.008 s | 0.02 s | Compresión semántica (solo ~8 frases únicas) |
| **Costeo** | 0.02 s | 0.09 s | Tarifa $2.50 / 1M tokens |
| **Reporte Excel** | 1.39 s | 6.88 s | `xlsxwriter` + una sola escritura + copia |
| **TOTAL PIPELINE** | **~2.3 s** | **~10.3 s** | **Reducción desde los 4 minutos iniciales (~23x)** |

Nota: sin optimización de tokens (`--no-optimize`) el total baja a ~9.1 s en 50k (se omiten traducción y `tokens_ingles`).

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

**Modo desarrollo con recarga automática:** el archivo `docker-compose.override.yml` (cargado automáticamente) monta `./app` en vivo y ejecuta `uvicorn --reload`. Editar código en `app/` recarga el servidor sin reiniciar el contenedor. Para desplegar sin auto-reload:

```bash
docker compose -f docker-compose.yml up -d --build
```

> Si se agregan nuevas dependencias Python, se requiere reconstruir la imagen (`docker compose up -d --build`); el volumen solo cubre el código.

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
4. Visualiza el avance etapa por etapa en tiempo real; las **métricas aparecen apenas termina el análisis**, mientras se genera el Excel el botón de descarga queda bloqueado y se habilita cuando el archivo está listo.
5. Al abrir la página se cargan los últimos resultados (`/api/results`); si no existe el Excel, las métricas se muestran con el botón de descarga bloqueado.

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
| 7 | `especialidad` | Especialidad médica identificada (input gana; extracción solo rellena vacíos) |
| 8 | `fecha_solicitada` | Referencia o fecha detectada (input gana; extracción solo rellena vacíos) |
| 9 | `preferencia_horario` | Turno u horario de preferencia |
| 10 | `tokens_original` | Tokens consumidos por el mensaje original |
| 11 | `tokens_limpio` | Tokens consumidos por la versión limpia |
| 12 | `tokens_ingles` | Tokens consumidos por la versión traducida |
| 13 | `costo_estimado_original` | Costo en USD de la variante original |
| 14 | `costo_estimado_limpio` | Costo en USD de la variante limpia |
| 15 | `costo_estimado_ingles` | Costo en USD de la variante traducida |
