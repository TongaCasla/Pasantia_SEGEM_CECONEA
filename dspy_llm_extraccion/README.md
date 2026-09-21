# ⚖️ Extracción de Embargos Judiciales con DSPy y LLMs Locales

Pipeline modular basado en **[DSPy](https://github.com/stanfordnlp/dspy)** para la extracción estructurada, validación y optimización de datos en oficios judiciales de embargo y medidas cautelares.

Diseñado para operar eficientemente con **LLMs locales** (ej. Qwen 2.5 / 3.5 vía LM Studio, Ollama o vLLM) o proveedores remotos compatibles con la API de OpenAI, garantizando privacidad documental y reproducibilidad.

---

## 🚀 Características Principales

- **Programación Declarativa con DSPy:** Reemplaza el *prompt engineering* manual y frágil por firmas tipadas (`dspy.Signature`) y módulos parametrizados (`dspy.Module`).
- **Optimización Automática de Demostraciones:** Compilación mediante algoritmos como `BootstrapFewShot` o `MIPROv2` para maximizar métricas sobre conjuntos de entrenamiento etiquetados.
- **Soporte Multi-Embargado:** Detección y asociación consistente de múltiples causantes en un mismo oficio (separación estructurada `|` y posterior desagregación).
- **Normalización y Métricas Especializadas:**
  - Tolerancia y homologación de DNI (dígitos limpios) y CUIT/CUIL.
  - Normalización de importes monetarios en formato argentino (`$ 1.234.567,89`) vs estándar (`1234567.89`).
  - Coincidencia difusa (*fuzzy matching*) y Jaccard para nombres propios.
- **Procesamiento Masivo y Resiliente:** Sistema de checkpoints periódicos en disco para pausar y reanudar ejecuciones en lotes de gran escala.

---

## 📁 Estructura del Proyecto

```text
dspy_llm_extraccion/
├── config/
│   └── embargo.yaml                      # Configuración de LLM, rutas, splits y optimizador
├── src/
│   ├── __init__.py
│   ├── modelos.py                        # Signatures DSPy (ExtraccionEmbargo)
│   ├── extractor.py                      # Módulo ExtraerEmbargo (Predict / ChainOfThought)
│   ├── metricas.py                       # Métricas compuestas y desglose de evaluación
│   ├── normalizacion.py                  # Limpieza de DNIs, CUITs, montos y textos
│   ├── dataset.py                        # Carga y split (train/val/test) de dspy.Example
│   └── utils.py                          # Checkpoints, cliente LM, logging y serialización
├── programas/                            # Artefactos compilados/optimizados (.json)
├── output/                               # Resultados de inferencia y reportes CSV
├── entrenar.py                           # CLI: Optimización y compilación de prompts
├── evaluar.py                            # CLI: Benchmarking y reporte detallado de aciertos
├── ejecutar.py                           # CLI: Inferencia en producción sobre lotes
├── bd_supervisada_embargos_actualizada.csv # Dataset de referencia (Golden Dataset)
├── frag_con_texto.csv                    # Textos completos de documentos judiciales
├── requirements.txt                      # Dependencias del entorno
└── README.md                             # Documentación del proyecto
```

---

## 🛠️ Instalación y Requisitos

### 1. Entorno de Python
Se recomienda Python 3.10 o superior:

```bash
pip install -r requirements.txt
```

Las dependencias principales son:
- `dspy >= 3.3.0`
- `pandas >= 2.0.0`
- `pyyaml >= 6.0`
- `tqdm >= 4.66.0`

### 2. Configuración del Servidor LLM Local (LM Studio / vLLM / Ollama)
Por defecto, el pipeline apunta a un endpoint local compatible con OpenAI:
- **URL Base:** `http://localhost:1234/v1`
- **Modelo:** Por ejemplo, `Qwen/Qwen2.5-7B-Instruct-GGUF` o `qwen2.5-coder-7b-instruct`
- **Contexto recomendado:** Al menos 8192 o 16384 tokens para abarcar oficios completos.

> Si utilizas otro servidor o API (por ej. Ollama en `http://localhost:11434/v1` o un endpoint remoto), ajusta los parámetros en `config/embargo.yaml`.

---

## ⚙️ Configuración (`config/embargo.yaml`)

El archivo YAML centraliza todo el comportamiento del pipeline:

```yaml
llm:
  api_base: "http://localhost:1234/v1"
  model: "openai/local-model"
  temperature: 0.0
  max_tokens: 1500
  api_key: "local"

datos:
  bd_supervisada: "bd_supervisada_embargos_actualizada.csv"
  frag_con_texto: "frag_con_texto.csv"
  campo_entrenamiento: "contexto"        # Fragmento representativo
  campo_produccion: "texto_completo"      # Documento judicial completo
  split:
    train: 0.60
    val: 0.20
    test: 0.20
    seed: 42
    priorizar_multiples: true

optimizador:
  metodo: "BootstrapFewShot"             # "BootstrapFewShot" o "MIPROv2"
  max_bootstrapped_demos: 4
  max_labeled_demos: 4
  max_rounds: 1

extraccion:
  cot: false                             # True para activar Chain of Thought
  max_chars: 12000                       # Truncamiento defensivo de documentos extensos
  max_reintentos: 2

rutas:
  programa_compilado: "programas/embargo_optimizado.json"
  output_default: "output/extraccion_embargos.csv"
```

---

## 📋 Campos Extraídos

El modelo extrae las siguientes variables clave de cada oficio judicial:

| Campo | Tipo | Descripción y Formato |
|---|---|---|
| `nombre_embargado` | `str` | Nombre y apellido o razón social del demandado. En casos múltiples: `PÉREZ JUAN\|GÓMEZ MARÍA`. |
| `dni` | `str` | Documento Nacional de Identidad (sólo dígitos, sin puntos). En casos múltiples: `20111222\|30444555`. |
| `cuit_cuil` | `str` | Identificador fiscal CUIT/CUIL (sólo dígitos). Mismo orden de ordenamiento que el nombre. |
| `monto_total` | `str` | Importe numérico total de la traba (suma de capital + costas/intereses presupuestados si aplica). |
| `monto_contexto` | `str` | Cita textual del oficio donde se explicitan los importes para fines de auditoría. |
| `cuenta` | `str` | Número de cuenta judicial o CBU de autos designada para el depósito. |

---

## 🎯 Flujo de Trabajo

### 1. Evaluación Inicial (Línea Base / Zero-Shot)
Evalúa el rendimiento inicial del LLM sin demostraciones previas sobre el split de prueba (`test`):

```bash
python evaluar.py --split test
```

Exportar los resultados detallados a un CSV para análisis de errores:
```bash
python evaluar.py --split test --output-csv output/eval_baseline_test.csv
```

### 2. Entrenamiento y Optimización con DSPy
Compila y selecciona las mejores demostraciones (*few-shot*) utilizando el optimizador `BootstrapFewShot`:

```bash
python entrenar.py --optimizer BootstrapFewShot --demos 4
```

Parámetros opcionales:
- `--eval-only`: Evalúa el baseline sin ejecutar la fase de optimización.
- `--campo texto_completo`: Entrena usando el texto completo en lugar del fragmento contextual.
- `--output programas/mi_modelo_optimizado.json`: Especifica la ruta destino del programa compilado.

El programa optimizado se guardará en `programas/embargo_optimizado.json`.

### 3. Evaluación del Programa Compilado
Compara la efectividad del programa optimizado frente al split de prueba:

```bash
python evaluar.py --prog programas/embargo_optimizado.json --split test --output-csv output/eval_optimizado_test.csv
```

### 4. Inferencia en Producción
Procesa lotes de documentos judiciales nuevos (o el archivo `frag_con_texto.csv`):

```bash
# Inferencia estándar usando el modelo optimizado
python ejecutar.py frag_con_texto.csv --prog programas/embargo_optimizado.json --output output/extraccion_final.csv

# Procesar una prueba rápida con los primeros 5 documentos
python ejecutar.py frag_con_texto.csv --limit 5

# Reiniciar ejecución ignorando checkpoints previos
python ejecutar.py frag_con_texto.csv --reset
```

> **Recuperación ante fallos:** `ejecutar.py` guarda automáticamente un checkpoint en `output/checkpoint_*.json`. Si la ejecución se interrumpe, basta con volver a ejecutar el comando sin el flag `--reset` para continuar desde el último documento procesado.

---

## 📊 Sistema de Métricas

La métrica principal (`metrica_embargo`) calcula un puntaje entre `0.0` y `1.0` ponderando los componentes críticos del oficio:

- **Personas (45%):**
  - Coincidencia difusa de Nombres (Jaccard + Levenshtein).
  - Coincidencia exacta de DNIs normalizados.
  - Coincidencia exacta de CUIT/CUIL.
  - Penalización por cantidad dispar de personas encontradas.
- **Monto Total (35%):**
  - Tolerancia de hasta un 2% de diferencia relativa o desvío menor a $500 pesos (para absorber discrepancias por redondeo de centavos o cálculo de intereses).
- **Cuenta Judicial (20%):**
  - Normalización y coincidencia exacta de cuentas bancarias y números de autos.
