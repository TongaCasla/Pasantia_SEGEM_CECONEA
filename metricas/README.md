# Evaluación de Métricas para Modelos PII / NER

Este módulo contiene los scripts y herramientas necesarias para evaluar y comparar cuantitativamente el desempeño de extracción de entidades sensibles (PII / NER) de tres modelos (**GLiNER2**, **Large_v25**, **PII_v1**) frente a una base de datos supervisada de referencia (`final_solicitud.csv`).

---

## 📁 Estructura del Módulo

```
metricas/
├── README.md                  # Documentación del módulo
├── calcular_metricas.py       # Script principal de evaluación
├── reporte_metricas.md        # Reporte completo en Markdown autogenerado
├── graficos/                  # Gráficos de barras comparativos (PNG)
│   ├── comparativa_global.png
│   ├── detalle_categorias.png
│   └── recall_por_etiqueta.png
└── extras/                    # CSVs con entidades extraídas que no están en la referencia
    ├── extras_gliner2.csv
    ├── extras_large_v25.csv
    └── extras_pii_v1.csv
```

---

## 🚀 Requisitos y Dependencias

Asegúrate de contar con Python 3.10+ y las siguientes librerías instaladas:

- `pandas`
- `thefuzz`
- `python-Levenshtein` (recomendado para acelerar `thefuzz`)
- `matplotlib`

Si utilizas el entorno virtual del proyecto (`.venv`):

```bash
..\script_extraccion\.venv\Scripts\pip.exe install pandas thefuzz python-Levenshtein matplotlib
```

---

## ⚙️ Cómo Ejecutar y Parámetros por Línea de Comandos (CLI)

El script `calcular_metricas.py` permite configurar todos sus parámetros mediante argumentos de consola.

### 1. Ejecución con parámetros por defecto

```bash
# Con entorno virtual del proyecto
..\script_extraccion\.venv\Scripts\python.exe calcular_metricas.py

# O con entorno activado
python calcular_metricas.py
```

### 2. Opciones y Parámetros Disponibles (`--help`)

| Argumento / Flag | Alias | Descripción | Valor por Defecto |
|---|---|---|---|
| `--referencia` | `-r` | Ruta al archivo CSV de referencia supervisada | `../final_solicitud.csv` |
| `--gliner2` | | Ruta al CSV de salida del modelo GLiNER2 | `../resultados/gliner2_output.csv` |
| `--large-v25` | | Ruta al CSV de salida del modelo Large_v25 | `../resultados/large_v25_output.csv` |
| `--pii-v1` | | Ruta al CSV de salida del modelo PII_v1 | `../resultados/pii_v1_output.csv` |
| `--umbral` | `-u` | Umbral de similitud (%) para fuzzy matching (`thefuzz`) | `85` |
| `--tolerancia-len` | `-t` | Diferencia máxima de longitud en caracteres | `3` |
| `--output-dir` | `-o` | Directorio donde guardar reporte, gráficos y extras | `.` (directorio actual) |
| `--separador` | `-s` | Separador de los archivos CSV | `;` |

### 3. Ejemplos de uso con argumentos personalizados

#### Cambiar el umbral de similitud a 90%:
```bash
python calcular_metricas.py -u 90
```

#### Cambiar la tolerancia de caracteres a ±5:
```bash
python calcular_metricas.py -t 5
```

#### Especificar rutas personalizadas de entrada y salida:
```bash
python calcular_metricas.py \
  --referencia "../mi_referencia.csv" \
  --gliner2 "../resultados/mi_gliner2.csv" \
  --umbral 90 \
  --output-dir "./output_experimento_1"
```

#### Ver el menú de ayuda:
```bash
python calcular_metricas.py --help
```

---

## 🎯 Criterios de Evaluación y Algoritmo de Matching

### 1. Campo de Comparación
El matching se realiza **únicamente contra la columna `valor`** de la referencia supervisada por cada archivo/documento (`id`). La columna `ocr_corregido` es informativa y no interviene en el cálculo.

### 2. Algoritmo de Coincidencia (Matching 1 a 1)
Por cada documento (`id`):
- **Coincidencia Exacta**: Se busca match exacto (`case-insensitive` y eliminando espacios extra) entre el `valor` del modelo y el `valor` de la referencia.
- **Coincidencia Parcial**: Si no hay match exacto, se evalúa la similitud usando `thefuzz.fuzz.ratio`:
  - Umbral de similitud: **≥ 85%** (configurable vía `--umbral`).
  - Diferencia de longitud de texto: **≤ 3 caracteres** (configurable vía `--tolerancia-len`).
- **Regla 1 a 1**: Cada entidad detectada por el modelo matchea como máximo con una entidad de la referencia y viceversa.

### 3. Clasificación de Etiquetas de la Referencia

| Clasificación | Etiquetas | Comportamiento |
|---|---|---|
| **Evaluables** | `persona`, `dni`, `cuit_cuil`, `cvu`, `cbu` | Forman parte del cálculo de Precision, Recall y F1. |

| **Opcionales** | `alias`, `persona_juridica` | Si el modelo las detecta correctamente, se suma la coincidencia; si NO las encuentra, **no se penaliza como error**. |
| **Excluidas** | `monto`, `rev_nombre` | Se ignoran de la evaluación. |

---

## 📊 Métricas Calculadas

- **Correctas (Exactas)**: Entidades con coincidencia exacta de texto.
- **Detecciones Parciales**: Entidades coincidentes por fuzzy matching (≥ umbral).
- **No Encontradas (Error)**: Entidades de la referencia supervisada que el modelo omitió.
- **Extras (Identificación Errónea)**: Entidades detectadas por el modelo que no corresponden a ninguna entidad de la referencia.
- **Precision**: $\frac{\text{Correctas} + \text{Parciales}}{\text{Correctas} + \text{Parciales} + \text{Extras}}$
- **Recall**: $\frac{\text{Correctas} + \text{Parciales}}{\text{Total Referencia Evaluable}}$
- **F1-Score**: $2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$

---

## 📑 Archivos CSV de Entidades Extras

Los archivos en la carpeta `extras/` contienen el detalle completo de las entidades que el modelo detectó pero que no estaban presentes en la referencia supervisada:

- `extras/extras_gliner2.csv`
- `extras/extras_large_v25.csv`
- `extras/extras_pii_v1.csv`

Formato separado por `;` (o el indicado en `--separador`) con columnas:
`numero_archivo;id;nombre_archivo;clasificacion;etiqueta;valor;span_inicio;span_fin;score`
