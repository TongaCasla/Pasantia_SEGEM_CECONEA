# Extracción de Entidades PII con GLiNER

Este módulo contiene un script de Python diseñado para identificar y extraer entidades de Información Personal Identificable (PII) a partir de documentos estructurados en formato JSON o CSV. 

El modelo preentrenado utilizado es [`fastino/gliner2-privacy-filter-PII-multi`](https://huggingface.co/fastino/gliner2-privacy-filter-PII-multi), optimizado para la detección multilingüe de información confidencial.

## Características

* **Soporte de Formatos**: Entrada en formato JSON (como objeto, lista o JSON Lines) y CSV.
* **Procesamiento de Documentos Largos**: Divide el texto en fragmentos (chunks) con solapamiento inteligente para no superar la ventana de contexto del modelo ni omitir entidades en los bordes.
* **Deduplicación**: Combina y deduplica entidades redundantes que caen en las áreas de superposición.
* **Formatos de Salida Simultáneos**: 
  - **JSON**: Conserva la estructura de entrada original, agregando una lista ordenada de entidades con sus posiciones de inicio/fin y confidencialidad.
  - **CSV**: Genera un archivo plano con una fila por entidad detectada, ideal para análisis y tabulación rápida.
* **Soporte de Dispositivo**: Detección automática y uso de GPU (`CUDA`) si está disponible para acelerar el procesamiento.

---

## Entidades Detectadas (Etiquetas)

El script busca y clasifica las siguientes entidades PII:
1. `person` (Nombres de personas)
2. `national_id_number` (Número de documento nacional de identidad, DNI)
3. `government_id` (Identificaciones gubernamentales generales)
4. `tax_id` (Identificación tributaria como CUIL, CUIT, RFC, etc.)
5. `bank_account` (Números de cuentas bancarias)
6. `account_number` (Números de cuentas generales)

---

## Instrucciones de Uso en Google Colab

Puedes clonar este repositorio y ejecutarlo directamente en Google Colab conectándolo con tu Google Drive para los archivos de entrada/salida.

### Celda 1: Clonar el Repositorio e Instalar Dependencias

```python
# 1. Clonar el repositorio
!git clone https://github.com/<tu-usuario>/<tu-repo>.git

# 2. Ir a la carpeta del proyecto
%cd <tu-repo>/ExtraccionGLiner

# 3. Instalar las dependencias
!pip install -r requirements.txt
```

### Celda 2: Montar Google Drive

```python
from google.colab import drive
drive.mount('/content/drive')
```

### Celda 3: Ejecutar la Extracción

Ejecuta el script especificando la ubicación de tus archivos de entrada y la carpeta de salida en Google Drive:

```python
!python extraccion_gliner.py \
    --input "/content/drive/MyDrive/datos/input.json" \
    --output "/content/drive/MyDrive/resultados/" \
    --text-column "texto_limpio" \
    --threshold 0.5
```

---

## Argumentos de Consola

| Argumento | Obligatorio | Por Defecto | Descripción |
| :--- | :---: | :---: | :--- |
| `--input` | Sí | - | Ruta al archivo `.json` o `.csv` de entrada. |
| `--output` | Sí | - | Ruta a la carpeta de salida (donde se crearán los archivos procesados). |
| `--text-column` | No | `texto_limpio` | Nombre de la columna o clave en el dataset que contiene el texto a analizar. |
| `--threshold` | No | `0.5` | Umbral de confianza mínimo (de 0 a 1) para aceptar una entidad detectada. |
| `--chunk-size` | No | `1500` | Tamaño de ventana máximo en caracteres por bloque de procesamiento. |
| `--overlap` | No | `150` | Superposición en caracteres entre fragmentos de texto para evitar cortes abruptos. |

---

## Formato de los Resultados

Si tu archivo de entrada se llama `dataset_ejemplo.json`, la ejecución generará dos archivos en el directorio de salida:

### 1. `dataset_ejemplo_gliner_pii.json`
Un archivo JSON estructurado que conserva los metadatos `id`, `nombre` y `clasificacion` de cada documento y añade las entidades detectadas:

```json
[
  {
    "id": "494149",
    "nombre": "Solicitud de informacion de usuarios",
    "clasificacion": "Oficio",
    "texto_analizado": "...",
    "entities": [
      {
        "text": "Juan Pérez",
        "label": "person",
        "score": 0.9412,
        "start": 12,
        "end": 22
      }
    ]
  }
]
```

### 2. `dataset_ejemplo_gliner_pii.csv`
Un archivo CSV aplanado ideal para su visualización o carga en planillas de cálculo (Excel, Sheets, Pandas):

| id | nombre | clasificacion | entity_text | entity_label | entity_score | start_char | end_char |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 494149 | Solicitud de informacion de usuarios | Oficio | Juan Pérez | person | 0.9412 | 12 | 22 |
| 494149 | Solicitud de informacion de usuarios | Oficio | 20-33445566-9 | tax_id | 0.8876 | 45 | 58 |
