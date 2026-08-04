# Extracción de Entidades PII Multi-Modelo con GLiNER (V3)

Este script permite la extracción automática de Información de Identificación Personal (PII) a partir de archivos CSV utilizando tres modelos diferentes basados en la tecnología de reconocimiento de entidades **GLiNER** y **GLiNER2**.

---

## Novedades en V3
- **Resolución Flexible de Spans**: Se incorporó el algoritmo `_find_flexible_span` que resuelve posiciones precisas (`span_inicio`, `span_fin`) mediante expresiones regulares que ignoran saltos de línea (`\n`) y espacios múltiples.
- **Eliminación de Spans Erróneos en 0**: Evita asignar de forma falsa `span_inicio = 0` cuando un modelo como `gliner2` extrae entidades separadas por saltos de línea o cuando la búsqueda exacta estricta fallaba.

---

## Modelos Soportados

El script permite ejecutar y comparar los siguientes modelos:

1. **`gliner2`**: `fastino/gliner2-privacy-filter-PII-multi` (especializado en PII, usa la librería `gliner2`).
2. **`pii_v1`**: `urchade/gliner_multi_pii-v1` (multilingüe especializado en PII, usa la librería `gliner`).
3. **`large_v25`**: `gliner-community/gliner_large-v2.5` (modelo zero-shot generalista, usa la librería `gliner`).

El script detecta dinámicamente qué librería de Python debe utilizar según el modelo configurado.

---

## Requisitos e Instalación

Para instalar las dependencias necesarias de Python, ejecuta:

```bash
pip install -r requirements.txt
```

*Nota: Se recomienda utilizar un entorno virtual (venv o conda).*

---

## Formato del CSV de Entrada

El CSV de entrada debe tener codificación **UTF-8** y utilizar un separador (por defecto `;`). Los campos mínimos requeridos son:
- **`id`**: Identificador del registro. El script lo utiliza para generar el índice secuencial `numero_archivo`.
- **`nombre_archivo`**: Nombre de referencia.
- **`clasificacion`**: Información o etiqueta de clasificación del registro.
- **`texto_limpio`**: Columna que contiene el cuerpo de texto del cual se extraerán las entidades. *(Se puede parametrizar si tu columna tiene otro nombre).*

---

## Parámetros de Ejecución (CLI)

```bash
python extract_pii_v3.py --input <ruta_csv> [opciones]
```

### Opciones Disponibles:

| Parámetro | Valor por defecto | Descripción |
| :--- | :--- | :--- |
| `--input` | *(Requerido)* | Ruta al archivo CSV con los datos a procesar. |
| `--output-dir` | `.` | Directorio donde se crearán y guardarán los resultados. |
| `--threshold` | `0.5` | Umbral de confianza mínimo (de `0.0` a `1.0`) para aceptar una detección. |
| `--chunk-size` | `384` | Tamaño de ventana en tokens para fragmentar textos largos. |
| `--chunk-overlap` | `64` | Solapamiento en tokens entre ventanas consecutivas. |
| `--normalize` | `none` | Modo de normalización de entrada (`none`, `light`, `aggressive`). Re-mapea spans al texto original. |
| `--batch-size` | `8` | Tamaño de lote para inferencia batch por chunks en `gliner2`. |
| `--model` | `gliner2` | Uno o más modelos a ejecutar (ej: `gliner2`, `pii_v1`, `large_v25`). Usa `all` para ejecutarlos todos. |
| `--text-column` | `texto_limpio` | Nombre de la columna que contiene el texto en el CSV de entrada. |
| `--separator` | `;` | Caracter delimitador del CSV de entrada. |
| `--device` | `cpu` | Dispositivo de procesamiento: `cpu` o `cuda` (GPU). |

---

## 📁 ¿Cómo funcionan los Outputs y Nombres Automáticos?

1. **Ubicación de Salida y Carpeta del Experimento (`--output-dir`)**:
   El argumento `--output-dir` especifica el directorio base de salida (por defecto `.`). En cada ejecución, el script crea automáticamente una subcarpeta dentro de `--output-dir` nombrada según los parámetros del experimento y la marca de tiempo:
   
   $$\text{\{Confianza\}\_\{ChunkSize\}\_\{Overlap\}\_\{DDMMAAAAHHMMSS\}}$$
   
   *Ejemplo*: `../resultados/80_384_64_03082026120723/`

2. **Nombres Automáticos de Archivos**:
   Dentro de la subcarpeta creada para el experimento, los archivos generados mantienen la identificación del modelo y la parametrización:
   
   $$\text{\{Confianza\}\_\{ChunkSize\}\_\{Overlap\}\_\{Modelo\}\_\{DDMMAAAAHHMMSS\}.csv / .json}$$

   - **Confianza**: Valor entero en porcentaje (`0.8` $\to$ `80`, `0.5` $\to$ `50`, `0.85` $\to$ `85`).
   - **Chunk Size**: Tamaño de ventana en tokens (ej: `384`).
   - **Overlap**: Solapamiento en tokens (ej: `64`).
   - **Modelo**: Prefijo identificador (`gliner2`, `pii_v1` o `large_v25`).
   - **Timestamp**: Fecha y hora de ejecución en formato `DDMMAAAAHHMMSS` (ej: `03082026120723`).

---

## Ejemplos de Uso

### 1. Ejecutar todos los modelos enviando los resultados a la carpeta `../resultados`:
```bash
python extract_pii_v2.py --input input_solicitud.csv --output-dir ../resultados --model all --threshold 0.8 --chunk-size 384 --chunk-overlap 64 --device cuda
```

**Genera la subcarpeta**: `../resultados/80_384_64_03082026120723/` conteniendo:
- `80_384_64_gliner2_03082026120723.csv` y `80_384_64_gliner2_03082026120723.json`
- `80_384_64_pii_v1_03082026120723.csv` y `80_384_64_pii_v1_03082026120723.json`
- `80_384_64_large_v25_03082026120723.csv` y `80_384_64_large_v25_03082026120723.json`

### 2. Ejecutar con confianza de 0.5 y guardar en la carpeta actual:
```bash
python extract_pii_v2.py --input input_solicitud.csv --model gliner2 --threshold 0.5
```
**Genera la subcarpeta**: `./50_384_64_03082026120723/` conteniendo:
- `50_384_64_gliner2_03082026120723.csv` y `50_384_64_gliner2_03082026120723.json`

---

## Estructura del CSV de Salida

`numero_archivo;id;nombre_archivo;clasificacion;texto_limpio;etiqueta;valor;span_inicio;span_fin;score`

### Normalización de Etiquetas:
- Nombres de personas $\to$ `person`
- Documentos de identidad nacionales / DNI $\to$ `national_id_number`
- Números de identificación fiscal / Tax ID $\to$ `tax_id`
- Cuentas bancarias $\to$ `bank_account`
- Números de seguridad social $\to$ `social_security_number`
- Información genérica de Gobierno $\to$ `government_id`
- Números genéricos de cuenta $\to$ `account_number`
