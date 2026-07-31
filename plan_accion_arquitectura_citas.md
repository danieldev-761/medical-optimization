# Plan de acción, arquitectura y criterios de aceptación

## Contexto y objetivo

Este documento define el plan de acción, la arquitectura propuesta y los criterios de aceptación para la historia de usuario HU-015, orientados a priorizar rapidez de ejecución sin perder trazabilidad funcional ni capacidad de análisis económico. La solución debe procesar solicitudes de citas médicas desde archivos Excel individuales o por carpeta, evaluar opcionalmente la tokenización en español frente a inglés, y producir tanto una salida estructurada en Excel como una interfaz con resumen y gráficas de costo y tokens [cite:2].

El objetivo técnico principal es reducir el tiempo total de procesamiento sobre cargas masivas mediante una pipeline por etapas, saneamiento temprano de datos, conversión temprana a CSV, análisis focalizado exclusivamente sobre la columna `mensaje_texto`, y uso selectivo de concurrencia para tareas I/O-bound [cite:2][cite:28][cite:32].

## Alcance funcional

La solución aceptará dos modos de entrada: un archivo `.xlsx` único o una carpeta local con múltiples archivos `.xlsx`, consolidando el contenido antes del análisis [cite:2]. Antes de cualquier procesamiento semántico, el sistema validará que las columnas requeridas estén presentes y que `mensaje_texto` pueda ser parseado correctamente [cite:2].

La salida final tendrá dos entregables principales:

- Un Excel de una sola hoja con los resultados estructurados por fila procesada.
- Una página web con resumen ejecutivo, KPIs y gráficas de análisis basadas en los resultados reales del procesamiento y en la proyección hipotética definida por el TL [cite:2].

## Decisiones funcionales cerradas

Las decisiones acordadas para el diseño son las siguientes:

- El archivo de entrada puede ser `.xlsx` único o una carpeta de `.xlsx` [cite:2].
- El procesamiento interno usará CSV como formato intermedio para reducir sobrecarga frente a Excel [cite:32].
- Solo la columna `mensaje_texto` será sometida a limpieza semántica, tokenización y traducción; las demás columnas se preservan como datos estructurados y de trazabilidad [cite:2].
- El sistema limpiará filas vacías, nulas o sin valor semántico antes de las etapas costosas [cite:2].
- Las acciones válidas a extraer serán `confirmar`, `cancelar` y `reprogramar`.
- `fecha_solicitada` y `preferencia_horario` podrán quedar vacíos cuando no estén explícitamente presentes en el mensaje [cite:2].
- La salida final en Excel tendrá una sola hoja.
- El dashboard mostrará análisis real y análisis hipotético usando la tarifa de 2.50 USD por millón de tokens y una proyección de 15,000 mensajes por día [cite:2].

## Definición de `optimizar_tokens`

El parámetro `optimizar_tokens` define dos comportamientos distintos dentro de la pipeline [cite:2].

### `optimizar_tokens = False`

Cuando el parámetro esté desactivado, el sistema realizará únicamente validación básica de integridad y procesará el mensaje original en español. En este modo no se ejecutará arbitraje de costo, ni comparación entre variantes, ni limpieza orientada específicamente a reducción de tokens [cite:2].

### `optimizar_tokens = True`

Cuando el parámetro esté activado, el sistema ejecutará una etapa previa de evaluación de costo y tokenización sobre tres variantes del mismo `mensaje_texto`:

1. Texto original en español.
2. Texto limpio u optimizado en español.
3. Texto traducido al inglés a partir de la versión limpia.

En este modo, la traducción ocurrirá siempre sobre `mensaje_texto` limpio y no sobre las demás columnas. Luego se registrarán tokens y costos estimados para las tres variantes, tanto para el Excel final como para el dashboard [cite:2].

## Arquitectura propuesta

La arquitectura recomendada es modular y por etapas, priorizando separación de responsabilidades, facilidad de profiling y reducción temprana del volumen a procesar. El flujo general se divide en ingestión, normalización, preprocesamiento, análisis lingüístico, análisis económico y presentación de resultados [cite:2].

### Capas del sistema

| Capa | Responsabilidad |
|---|---|
| Ingesta | Cargar archivo `.xlsx` individual o escanear carpeta y consolidar archivos [cite:2] |
| Normalización | Convertir `.xlsx` a CSV y estandarizar columnas |
| Preprocesamiento | Validar filas, filtrar vacíos, limpiar ruido, deduplicar mensajes |
| Extracción | Detectar `accion`, `especialidad`, `fecha_solicitada` y `preferencia_horario` |
| Tokenización | Calcular `tokens_original`, `tokens_limpio`, `tokens_ingles` con `o200k_base` [cite:2] |
| Traducción | Traducir solo `mensaje_texto` limpio cuando `optimizar_tokens=True` [cite:2] |
| Costeo | Calcular costos estimados con tarifa de 2.50 USD por millón [cite:2] |
| Presentación | Generar Excel final y dashboard con KPIs y gráficas |

## Pipeline detallada

La secuencia recomendada es la siguiente:

1. Cargar uno o varios archivos `.xlsx` [cite:2].
2. Convertir inmediatamente cada archivo a CSV para trabajo interno más rápido [cite:32].
3. Validar columnas obligatorias, especialmente `paciente_id` y `mensaje_texto` [cite:2].
4. Filtrar filas vacías, nulas o con texto sin valor útil.
5. Normalizar `mensaje_texto` con limpieza semántica.
6. Deduplicar mensajes equivalentes tras normalización.
7. Extraer `accion`, `especialidad`, `fecha_solicitada` y `preferencia_horario` cuando estén presentes [cite:2].
8. Calcular tokens del texto original.
9. Calcular tokens del texto limpio.
10. Si `optimizar_tokens=True`, traducir el texto limpio al inglés y calcular `tokens_ingles` [cite:2].
11. Calcular costos por variante.
12. Generar Excel final y dashboard con resultados agregados [cite:2].

## Estrategia de rendimiento

La optimización del tiempo total debe basarse en cuatro principios: reducir I/O pesado, evitar trabajo inútil, concentrar el análisis en una sola columna y aplicar concurrencia únicamente donde realmente aporte [cite:28][cite:32].

### Decisiones de rendimiento

- Convertir Excel a CSV al inicio para disminuir costo de lectura y procesamiento posterior [cite:32].
- Procesar solo `mensaje_texto` en las etapas lingüísticas para no desperdiciar tiempo sobre columnas estructurales [cite:2].
- Eliminar filas vacías y ruido textual antes de tokenizar, traducir o analizar [cite:2].
- Deduplicar textos normalizados para evitar recalcular traducción o tokenización en mensajes repetidos.
- Medir tiempos por etapa para identificar cuellos de botella reales.

### Uso recomendado de concurrencia

`ThreadPoolExecutor` está recomendado para tareas I/O-bound, mientras que tareas CPU-bound pueden requerir procesos en lugar de hilos [cite:28]. En esta solución se propone:

- Usar `ThreadPoolExecutor` para conversión paralela de múltiples archivos, llamadas a traducción y llamadas a `/api/analyze`, ya que estas etapas dependen de espera de disco o red [cite:28].
- Mantener secuencial o por lotes la validación y limpieza inicial, porque esa fase reduce el volumen antes de la concurrencia.
- Evaluar `ProcessPoolExecutor` solo si la tokenización local demuestra ser el cuello de botella real del sistema [cite:28].
- Controlar el número de workers para no saturar memoria ni servicios externos, ya que el envío masivo de tareas puede crecer sin bloqueo si no se limita explícitamente [cite:24].

### Configuración inicial sugerida

La configuración inicial sugerida para una primera versión medible es:

- Batch size de 500 a 1000 filas para limpieza y tokenización local.
- `max_workers=4` para conversión concurrente de múltiples archivos.
- `max_workers=8` para traducción y `/api/analyze`, sujeto a pruebas de rate limiting [cite:24][cite:28].
- Timeouts y reintentos controlados para servicios externos.
- Caché por texto limpio para evitar reprocesar mensajes equivalentes.

## Heurísticas de limpieza semántica

La limpieza del `mensaje_texto` debe buscar reducción de ruido sin pérdida de significado operativo. No se trata de truncar agresivamente después de cualquier punto o coma, sino de eliminar segmentos que no alteren la intención, la especialidad ni las preferencias temporales [cite:2].

La limpieza debería contemplar:

- Eliminación de espacios duplicados y caracteres residuales.
- Remoción de frases accesorias o cortesías sin valor operacional.
- Conservación de términos de intención, especialidad, fecha y horario.
- Preservación de referencias como “próxima semana”, “viernes”, “mañana”, “tarde” o similares cuando aporten información útil [cite:2].
- Exclusión de filas cuyo mensaje quede vacío tras la limpieza.

## Contrato de salida en Excel

El Excel final tendrá una sola hoja con las siguientes columnas, en este orden:

| Columna | Descripción |
|---|---|
| `paciente_id` | Identificador del paciente |
| `accion` | Valor extraído: `confirmar`, `cancelar` o `reprogramar` |
| `especialidad` | Especialidad detectada en el mensaje o vacía si no aparece |
| `fecha_solicitada` | Fecha o referencia temporal relevante si está presente |
| `preferencia_horario` | Preferencia horaria si está presente; vacía si no aparece [cite:2] |
| `tokens_original` | Tokens del `mensaje_texto` original |
| `tokens_limpio` | Tokens del `mensaje_texto` limpio |
| `tokens_ingles` | Tokens del texto limpio traducido al inglés |
| `costo_estimado_original` | Costo estimado de la variante original |
| `costo_estimado_limpio` | Costo estimado de la variante limpia |
| `costo_estimado_ingles` | Costo estimado de la variante en inglés |

## Dashboard y analítica

La página web mostrará dos vistas analíticas complementarias: análisis real del procesamiento ejecutado y análisis hipotético para volumen proyectado. Ambas usarán la tarifa de 2.50 USD por millón de tokens [cite:2].

### KPIs obligatorios

Los KPIs mínimos sugeridos son:

- Total de filas leídas.
- Total de filas válidas.
- Total de filas descartadas.
- Tokens totales originales.
- Tokens totales limpios.
- Tokens totales en inglés.
- Costo total original.
- Costo total limpio.
- Costo total inglés.
- Ahorro absoluto y porcentual frente al original.

### Gráficas obligatorias

Las gráficas mínimas sugeridas son:

- Barras comparativas de tokens por variante.
- Barras comparativas de costo por variante.
- Proyección hipotética diaria, mensual, trimestral y anual para 15,000 mensajes por día [cite:2].
- Comparación de ahorro estimado entre original, limpio e inglés.

## Cálculo económico

La fórmula base de costeo será:

`costo_estimado = (tokens / 1,000,000) * 2.50`

Sobre esa base se calcularán dos bloques analíticos:

1. **Proceso real:** costo total observado en el lote realmente procesado, usando las columnas exportadas en el Excel [cite:2].
2. **Volumen hipotético:** proyección diaria, mensual, trimestral y anual para 15,000 mensajes por día, usando como base el promedio real de tokens por mensaje para cada variante [cite:2].

## Plan de acción

### Fase 1. Definición del contrato de datos

- Confirmar columnas mínimas de entrada.
- Normalizar nombres de columnas esperadas.
- Definir representación de vacíos y errores de parseo.
- Cerrar el esquema de salida del Excel.

### Fase 2. Ingesta y normalización

- Implementar carga de archivo único y carga por carpeta [cite:2].
- Convertir `.xlsx` a CSV como primer paso persistente.
- Consolidar múltiples archivos cuando aplique.

### Fase 3. Limpieza y preprocesamiento

- Filtrar filas vacías o no procesables.
- Limpiar ruido del `mensaje_texto`.
- Deduplicar mensajes normalizados.
- Registrar métricas de reducción de volumen.

### Fase 4. Extracción y análisis

- Extraer `accion`, `especialidad`, `fecha_solicitada` y `preferencia_horario` cuando estén presentes.
- Calcular tokens del texto original y del texto limpio.
- Traducir el texto limpio al inglés cuando `optimizar_tokens=True` [cite:2].
- Calcular `tokens_ingles` y los costos estimados de las tres variantes.

### Fase 5. Rendimiento y paralelismo

- Incorporar batches de procesamiento.
- Aplicar `ThreadPoolExecutor` solo en tareas I/O-bound [cite:28].
- Medir tiempos por etapa.
- Ajustar batch size y workers con pruebas reales.

### Fase 6. Presentación de resultados

- Exportar Excel final de una sola hoja.
- Generar dashboard con KPIs y gráficas.
- Mostrar análisis real e hipotético con la misma base tarifaria [cite:2].

## Criterios de aceptación

### Criterio 1. Carga flexible y validación

- El sistema permite cargar un archivo `.xlsx` individual o escanear una carpeta local con múltiples `.xlsx` [cite:2].
- Las columnas obligatorias se validan antes del análisis, especialmente `paciente_id` y `mensaje_texto` [cite:2].
- Los archivos se convierten a CSV antes del procesamiento interno.

### Criterio 2. Limpieza y reducción de volumen

- Las filas vacías, nulas o sin valor semántico son descartadas antes de tokenización y traducción.
- La limpieza semántica reduce ruido sin eliminar intención, especialidad, fecha ni preferencia horaria relevantes.
- Solo la columna `mensaje_texto` se procesa en limpieza, tokenización y traducción.

### Criterio 3. Modo `optimizar_tokens`

- Si `optimizar_tokens=False`, el sistema procesa el mensaje original en español sin arbitraje adicional [cite:2].
- Si `optimizar_tokens=True`, el sistema calcula tokens y costo del original, del limpio y del inglés traducido a partir del texto limpio [cite:2].
- En `optimizar_tokens=True`, la traducción se ejecuta siempre sobre `mensaje_texto` limpio.

### Criterio 4. Salida estructurada

- El sistema genera un Excel de una sola hoja.
- El Excel contiene exactamente las columnas acordadas en el orden definido.
- `fecha_solicitada` y `preferencia_horario` pueden quedar vacíos si no se mencionan explícitamente en el mensaje [cite:2].
- Los costos estimados se calculan con tarifa de 2.50 USD por millón de tokens [cite:2].

### Criterio 5. Dashboard analítico

- La página muestra KPIs de volumen, tokens, costos y ahorro.
- La página muestra gráficas de comparación entre original, limpio e inglés.
- La página incluye proyección diaria, mensual, trimestral y anual para 15,000 mensajes por día usando la misma tarifa de referencia [cite:2].
- La página distingue claramente análisis real y análisis hipotético.

### Criterio 6. Rendimiento

- El sistema aplica procesamiento por lotes.
- El sistema usa concurrencia solo en tareas I/O-bound donde aporte mejora medible [cite:28].
- El tiempo por etapa queda instrumentado para profiling.
- La solución evita reprocesar traducciones o análisis de mensajes equivalentes cuando exista caché disponible.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Traducción por fila demasiado lenta | Alto | Batching, `ThreadPoolExecutor`, caché, deduplicación [cite:28] |
| Sobrecarga por trabajar directo sobre `.xlsx` | Alto | Conversión temprana a CSV [cite:32] |
| Pérdida de información por limpieza agresiva | Alto | Heurísticas conservadoras y validación sobre campos extraídos |
| Saturación de servicios externos | Medio | Límites de workers, timeout, reintentos y control de cola [cite:24][cite:28] |
| Tokenización como cuello CPU-bound | Medio | Profiling y posible evaluación de `ProcessPoolExecutor` [cite:28] |

## Recomendación final

La implementación debe comenzar por una versión medible y perfilable, no por una optimización prematura. La prioridad correcta es reducir el volumen antes de la parte costosa, procesar exclusivamente `mensaje_texto`, usar CSV como formato intermedio, y aplicar concurrencia controlada únicamente en las etapas I/O-bound donde Python puede obtener mejoras reales [cite:24][cite:28][cite:32].
