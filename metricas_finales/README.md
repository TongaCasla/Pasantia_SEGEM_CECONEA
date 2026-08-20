# Módulo de Evaluación de Métricas Finales NER / PII

Este módulo calcula y genera métricas de desempeño (Precision, Recall y F1-Score) sobre la extracción de entidades nombradas (NER / PII), comparando extracciones automáticas contra una **Base de Datos Supervisada (Ground Truth)**.

Se realiza una evaluación en **dos canales independientes**:
1. **Modelos GLiNER (`persona`)**: Se evalúa la lista de personas únicas por archivo extraídas por modelos GLiNER utilizando comparación difusa (*fuzzy matching* con RapidFuzz).
2. **Extracción Regex (`dni` y `cuit_cuil`)**: Se evalúan las extracciones numéricas de expresiones regulares mediante coincidencia exacta sobre dígitos normalizados.

---

## 📁 Estructura de Archivos e Entradas

### 1. Base de Datos Objetivo (Ground Truth)
- **Archivo por defecto**: `bd_supervisada_conjunta_v3.csv`
- **Estructura**:
  `numero_archivo;id;nombre_archivo;clasificacion;texto_limpio;cantidad_entidades_encontradas;etiqueta;valor;ocr_corregido;span_inicio;span_fin;Aux`
- **Regla para `persona`**: Se construye la lista de personas únicas por documento (`id`) a partir del campo `ocr_corregido` (el nombre más completo presente en el archivo).
- **Regla para `dni` y `cuit_cuil`**: Se toma directamente el campo `valor`.

### 2. Extracciones de Modelos GLiNER (`extraccion_modelos/`)
- Contiene los archivos CSV de extracciones realizadas por distintos modelos GLiNER.
- **Estructura**:
  `numero_archivo;id;nombre_archivo;clasificacion;texto_limpio;etiqueta;valor;span_inicio;span_fin;score`
- Se evalúa únicamente la etiqueta `persona`. El nombre del modelo se toma automáticamente del nombre de cada archivo CSV.

### 3. Extracciones Regex (`extraccion_regex/`)
- Contiene los archivos CSV de extracciones numéricas por expresiones regulares.
- **Estructura**:
  `numero_archivo;id;nombre_archivo;clasificacion;texto_limpio;cantidad_entidades_encontradas;etiqueta;valor;ocr_corregido;span_inicio;span_fin`
- Se evalúan únicamente las etiquetas `dni` y `cuit_cuil`.

---

## 🚀 Uso del Script

El script principal es **`calcular_metricas_finales.py`**.

```bash
python calcular_metricas_finales.py [OPCIONES]
```

### Ejemplo de Ejecución Completa

```bash
python calcular_metricas_finales.py \
  --referencia ../bd_supervisada_conjunta_v3.csv \
  --modelos-dir ./extraccion_modelos \
  --regex-dir ./extraccion_regex \
  --output-dir ./output \
  --umbral 85 \
  --tolerancia-len 3 \
  --scorer partial_ratio
```

---

## ⚙️ Parámetros y Opciones CLI

| Parámetro | Forma Corta | Descripción | Valor por Defecto |
|---|---|---|---|
| `--referencia` | `-r` | Ruta a la BD supervisada de referencia (CSV). | `../bd_supervisada_conjunta_v3.csv` |
| `--modelos-dir` | | Carpeta que contiene los CSVs de modelos GLiNER. | `./extraccion_modelos` |
| `--regex-dir` | | Carpeta que contiene los CSVs de Regex. | `./extraccion_regex` |
| `--output-dir` | `-o` | Directorio donde se guardarán los resultados. | `./output` |
| `--umbral` | `-u` | Umbral mínimo de similitud (%) para fuzzy matching de persona. | `85` |
| `--tolerancia-len` | `-t` | Tolerancia máxima de diferencia en caracteres (`±N`). | `3` |
| `--scorer` | | Algoritmo RapidFuzz (`partial_ratio`, `ratio`, `token_sort_ratio`, `token_set_ratio`). | `partial_ratio` |
| `--score-cutoff` | | Cutoff nativo de score en RapidFuzz (0.0 a 100.0). | `0.0` |
| `--separador` | `-s` | Delimitador de columnas en los CSVs. | `;` |

---

## 📊 Salidas Generadas

Cada ejecución genera una carpeta timestamped dentro del directorio de salida (ej. `output/reporte_20260819_172322/`):

1. **📄 Reporte PDF (`reporte_{timestamp}.pdf`)**:
   - Cuadro 1: Entidades objetivo de la BD ground truth.
   - Cuadro 2: Conteos (Total BD, Detectadas, No detectadas, Extras) para `persona` comparando modelos.
   - Cuadro 3: Cuadro de métricas (Precision, Recall, F1) para `persona`.
   - Cuadro 4: Conteos y métricas para `dni` y `cuit_cuil` del extractor regex.
   - Gráficos e histogramas embebidos.

2. **📝 Reporte Markdown (`reporte_{timestamp}.md`)**:
   - Resumen ejecutivo en tablas formato Markdown.

3. **📈 Gráficos PNG (`graficos/`)**:
   - `histograma_persona.png`: Comparativa de conteos por modelo para `persona`.
   - `histograma_numericas.png`: Comparativa de conteos para `dni` y `cuit_cuil`.
   - `metricas_comparativa.png`: Gráfico de barras comparando Precision, Recall y F1-Score.

4. **📁 Archivos CSV de Entidades**:
   - `detectadas_persona_{modelo}.csv`: Entidades de personas correctamente emparejadas.
   - `no_detectadas_persona_{modelo}.csv`: Personas de la referencia no encontradas por el modelo.
   - `extras_persona_{modelo}.csv`: Extracciones del modelo que no corresponden a la referencia.
   - `detectadas_numericas_regex.csv`, `no_detectadas_numericas_regex.csv`, `extras_numericas_regex.csv`: Detalle para DNI y CUIT/CUIL.

---

## 🛠️ Requisitos e Instalación

Asegurate de contar con Python 3.8+ y las siguientes librerías instaladas:

```bash
pip install pandas numpy rapidfuzz matplotlib fpdf2
```
