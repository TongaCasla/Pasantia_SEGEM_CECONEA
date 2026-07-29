# Extracción de Entidades PII con GLiNER2

Script en Python que usa el modelo [`fastino/gliner2-privacy-filter-PII-multi`](https://huggingface.co/fastino/gliner2-privacy-filter-PII-multi) para extraer entidades de información personal identificable (PII) desde un CSV.

## Entidades extraídas

| Etiqueta             | Descripción                                  |
| -------------------- | -------------------------------------------- |
| `person`             | Nombres de personas                          |
| `national_id_number` | Número de documento nacional (DNI, CI, etc.) |
| `government_id`      | Identificación gubernamental                 |
| `tax_id`             | Identificación tributaria (CUIT, CUIL, etc.) |
| `bank_account`       | Cuenta bancaria                              |
| `account_number`     | Número de cuenta                             |

> **Nota**: Las etiquetas `national_id_number`, `government_id` y `tax_id` se dedupliclan automáticamente (si un mismo dato aparece con múltiples etiquetas, se conserva solo una vez con la de mayor confianza). Lo mismo aplica para `bank_account` y `account_number`.

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

### Básico (CPU)

```bash
python extract_pii.py --input ../input_solicitud.csv
```

### Con GPU (Colab)

```bash
python extract_pii.py --input ../input_solicitud.csv --device cuda
```

### Todos los parámetros

```bash
python extract_pii.py \
    --input ../input_solicitud.csv \
    --output-csv resultados.csv \
    --output-json resultados.json \
    --text-column texto_limpio \
    --threshold 0.7 \
    --device cuda \
    --separator ";" \
    --chunk-size 384 \
    --chunk-overlap 64
```

## Parámetros

| Parámetro         | Default                                    | Descripción                             |
| ----------------- | ------------------------------------------ | --------------------------------------- |
| `--input`         | _(requerido)_                              | Ruta al CSV de entrada                  |
| `--output-csv`    | `output.csv`                               | Ruta del CSV de salida                  |
| `--output-json`   | `output.json`                              | Ruta del JSON de salida                 |
| `--text-column`   | `texto_limpio`                             | Columna del CSV con el texto a procesar |
| `--threshold`     | `0.5`                                      | Confianza mínima (0.0 a 1.0)            |
| `--separator`     | `;`                                        | Separador del CSV de entrada            |
| `--device`        | `cpu`                                      | Dispositivo: `cpu` o `cuda`             |
| `--model`         | `fastino/gliner2-privacy-filter-PII-multi` | Modelo de HuggingFace                   |
| `--chunk-size`    | `384`                                      | Tamaño de chunk para textos largos      |
| `--chunk-overlap` | `64`                                       | Solapamiento entre chunks               |

## Formato de entrada

CSV con separador `;` y al menos estas columnas:

```
id;nombre_archivo;clasificacion;texto_limpio
```

> Puede tener más columnas, solo se usa la indicada por `--text-column`.

## Formato de salida

### CSV (`output.csv`)

```
numero_archivo;id;nombre_archivo;clasificacion;texto_limpio;etiqueta;valor;span_inicio;span_fin;score
```

### JSON (`output.json`)

```json
[
  {
    "numero_archivo": 1,
    "id": 494149,
    "nombre_archivo": "Solicitud de informacion de usuarios",
    "clasificacion": "Oficio",
    "texto_limpio": "...",
    "etiqueta": "person",
    "valor": "AMPUGNANI Cristian Gabriel",
    "span_inicio": 120,
    "span_fin": 146,
    "score": 0.9823
  }
]
```
