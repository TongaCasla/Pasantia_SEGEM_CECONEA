# Extracción de Fragmentos (`ExtraccionFragmento`)

Librería en Python para buscar palabras clave en documentos legales (embargos, oficios, resoluciones) y extraer los fragmentos de texto que las rodean.

Se usa de dos formas:

- **Módulo importable (caja negra)**: recibe un `str`, devuelve objetos tipados. No lee ni escribe archivos. Pensado para pipelines, workers y APIs.
- **CLI batch**: procesa un CSV completo y genera los archivos de salida (retrocompatible con `extraer_embargo.py`).

---

## 🚀 Características

- **Búsqueda insensible a mayúsculas, tildes y puntos** (normalización NFD) sin alterar el texto original extraído: `D.N.I.` matchea `dni`.
- **Mapeo exacto de posiciones** entre texto normalizado y original.
- **Ventanas configurables** globales o por categoría, con extensión hasta delimitadores semánticos (`. `, `\n`) y recorte por símbolos o por palabra completa.
- **Reducción de falsos positivos** (opcional, `habilitar_reduccion`).
- **Agrupación de fragmentos superpuestos** por categoría (opcional, `habilitar_agrupacion`).
- **Contexto del documento** (`contexto_embargado`) a partir de un segundo set de palabras clave (opcional).
- **Cero dependencias externas**: solo librería estándar. Python 3.7+.

---

## 📂 Estructura del Proyecto

```text
extraccion_fragmento_embargo_prod/
│
├── extraccion_fragmento/      # Paquete importable
│   ├── __init__.py            # Expone ExtraccionFragmento, ExtractorConfig, Fragmento, ResultadoExtraccion
│   ├── __main__.py            # Permite: python -m extraccion_fragmento
│   ├── models.py              # ExtractorConfig y modelos de resultado (dataclasses)
│   ├── normalizer.py          # Normalización NFD, mapeo de índices y búsqueda de palabras clave
│   ├── window.py              # Cálculo de ventanas: extensión, corte y ajuste por palabra
│   ├── reduction.py           # Reducción de falsos positivos (opcional)
│   ├── merger.py              # Agrupación de fragmentos superpuestos y contexto del documento
│   ├── loaders.py             # Lectura de archivos .txt de configuración
│   ├── extractor.py           # Fachada ExtraccionFragmento (caja negra en memoria)
│   └── cli.py                 # Adaptador CLI / procesamiento batch de CSV
│
├── tests/                     # Tests unitarios (unittest)
├── extraer_embargo.py         # Entry point legacy (delega en extraccion_fragmento.cli)
├── palabras_clave.txt         # Palabras clave por categoría
├── palabras_contexto.txt      # Palabras clave para contexto_embargado
├── reduccion.txt              # Palabras de reducción (falsos positivos)
└── output/                    # Salidas del modo CLI (subcarpeta con timestamp por ejecución)
```

---

## 📦 Uso como Módulo (Caja Negra)

### 1. Uso básico

```python
from extraccion_fragmento import ExtraccionFragmento, ExtractorConfig

config = ExtractorConfig(
    chars_antes=200,
    chars_despues=300,
    habilitar_reduccion=True,    # filtro de falsos positivos
    habilitar_agrupacion=True,   # fusión de fragmentos superpuestos
)

# Desde los archivos .txt de configuración...
extractor = ExtraccionFragmento.from_files(
    keywords_path="palabras_clave.txt",
    reduction_path="reduccion.txt",               # opcional
    context_keywords_path="palabras_contexto.txt",  # opcional
    config=config,
)

resultado = extractor.extraer(texto_documento)

for frag in resultado.fragmentos_principales:
    print(frag.categoria, frag.palabra_clave, frag.fragmento)

for frag in resultado.fragmentos_reducidos:      # solo si habilitar_reduccion=True
    print("descartado por:", frag.palabra_reduccion)

print(resultado.categorias_faltantes)            # categorías sin ningún fragmento
```

### 2. Configuración en memoria (sin archivos)

Útil cuando las palabras clave vienen de una base de datos, variables de entorno o un servicio de configuración.

```python
extractor = ExtraccionFragmento(
    palabras_clave={
        "Datos_Embargado": ["dni", "cuil", "cuit"],
        "Montos": ["hasta cubrir la suma", "por la suma"],
    },
    palabras_reduccion=["juez", "dr.", "dra.", "letrado"],
    palabras_clave_contexto={"Datos_Embargado": ["decretase embargo sobre"]},
    config=ExtractorConfig(chars_por_categoria={"Montos": (50, 100)}),
)
```

Formatos aceptados para `palabras_clave` / `palabras_clave_contexto`:

| Formato | Ejemplo |
| :--- | :--- |
| Diccionario categoría → lista | `{"Montos": ["por la suma"]}` |
| Lista de diccionarios | `[{"palabra": "por la suma", "categoria": "Montos"}]` |
| Lista de tuplas | `[("por la suma", "Montos")]` |
| Lista de strings | `["por la suma"]` (categoría `sin_categoria`) |

### 3. Integración en un pipeline

> [!TIP]
> Instanciá el extractor **una sola vez** y reutilizalo para todos los documentos: las palabras clave y los patrones se preparan en la construcción. La instancia no guarda estado mutable entre llamadas a `extraer()`.

**Pandas:**

```python
import pandas as pd
from extraccion_fragmento import ExtraccionFragmento, ExtractorConfig

extractor = ExtraccionFragmento.from_files("palabras_clave.txt", "reduccion.txt")

df = pd.read_csv("documentos.csv", sep=";")
df["resultado"] = df["texto_limpio"].map(extractor.extraer)

# Una fila por fragmento
filas = [
    {"id": row.id, **frag.to_dict()}
    for row in df.itertuples()
    for frag in row.resultado.fragmentos_principales
]
fragmentos = pd.DataFrame(filas)
```

**Streaming / lotes grandes** (`extraer_lote` es un generador, no carga todo en memoria):

```python
for resultado in extractor.extraer_lote(leer_textos()):
    publicar(resultado.to_dict())   # cola, base de datos, API, etc.
```

**Tarea de orquestador (Airflow, Prefect, etc.):**

```python
def tarea_extraccion(textos: list[str]) -> list[dict]:
    extractor = ExtraccionFragmento.from_files("palabras_clave.txt", "reduccion.txt")
    return [r.to_dict() for r in extractor.extraer_lote(textos)]
```

**Batch de CSV desde código** (mismo comportamiento que el CLI, devuelve un resumen):

```python
from extraccion_fragmento.cli import procesar_csv, ErrorProcesamiento

resumen = procesar_csv(
    ruta_csv="entrada.csv", columna_texto="texto_limpio",
    ruta_palabras="palabras_clave.txt", chars_antes=200, chars_despues=200,
    ruta_salida="output_embargos.csv", ruta_reduccion="reduccion.txt",
)
print(resumen["ruta_salida"], resumen["documentos_procesados"])
```

### 4. Errores y logging

| Situación | Comportamiento |
| :--- | :--- |
| Archivo `.txt` inexistente en `from_files` | `FileNotFoundError` |
| Sin palabras clave | `ValueError` |
| Parámetro numérico negativo en `ExtractorConfig` | `ValueError` |
| Formato inválido en `chars_por_categoria` (string) | Se ignora la entrada y se emite `logging.warning` (logger `extraccion_fragmento.models`) |
| Texto vacío o `None` | Resultado vacío, sin error |

La caja negra **nunca** imprime por consola ni llama a `sys.exit`.

---

## ⚙️ `ExtractorConfig`

| Parámetro | Tipo | Default | Descripción |
| :--- | :--- | :--- | :--- |
| `chars_antes` | `int` | `200` | Caracteres antes de la coincidencia. |
| `chars_despues` | `int` | `200` | Caracteres después de la coincidencia. |
| `habilitar_reduccion` | `bool` | `True` | Activa la reducción de falsos positivos. Si es `False`, `fragmentos_reducidos` queda siempre vacío. |
| `habilitar_agrupacion` | `bool` | `True` | Fusiona fragmentos superpuestos/contiguos de la misma categoría. Si es `False`, 1 fragmento por coincidencia. |
| `separador` | `str` | `" \| "` | Separador de palabras clave en fragmentos agrupados y en `palabras_clave_contexto`. |
| `chars_por_categoria` | `dict` o `str` | `None` | Ventana por categoría: `{"Montos": (50, 100)}` o `"Montos:50:100"`. `(0, 0)` omite la categoría. |
| `delimitadores_extension` | `list[str]` o `str` | `None` | Delimitadores para extender el fragmento hacia afuera: `[". ", "\n"]` o `'". ", \n'`. |
| `max_distancia_extension` | `int` | `0` | Máximo de caracteres para la extensión (`0` = sin límite). |
| `simbolos_corte` | `list[str]` o `str` | `None` | Símbolos para recortar hacia adentro: `[",", ";"]` o `",;"`. |
| `max_distancia_corte` | `int` | `0` | Máximo de caracteres hacia adentro para buscar símbolo de corte (`0` = desactivado). |
| `chars_antes_contexto` | `int` | `200` | Caracteres antes para `contexto_embargado`. |
| `chars_despues_contexto` | `int` | `200` | Caracteres después para `contexto_embargado`. |
| `separador_contexto` | `str` | `"\n\n"` | Separador entre párrafos no contiguos de `contexto_embargado`. |
| `categoria_reduccion` | `str` | `"datos_embargado"` | Categoría (prefijo, normalizado) sobre la que aplica la reducción. |
| `claves_requieren_numero` | `tuple[str]` | `("dni", "cuil", "cuit", "doc")` | Si la palabra clave contiene alguno de estos términos y no hay dígitos después de ella dentro del fragmento, se reduce con motivo `sin_numero`. |

### Reducción de falsos positivos

Aplica **solo** a la categoría `categoria_reduccion`. Un fragmento pasa a `fragmentos_reducidos` si:

1. Su palabra clave está en `claves_requieren_numero` y no aparece ningún dígito después de ella dentro del fragmento → `palabra_reduccion = "sin_numero"`.
2. El fragmento (normalizado) contiene alguna palabra de reducción → `palabra_reduccion = <palabra>`.

### Modelos de resultado

**`ResultadoExtraccion`**

| Campo | Tipo | Descripción |
| :--- | :--- | :--- |
| `fragmentos_principales` | `list[Fragmento]` | Fragmentos válidos, ordenados por posición. |
| `fragmentos_reducidos` | `list[Fragmento]` | Fragmentos descartados por reducción. |
| `contexto_embargado` | `str` | Párrafos de contexto del documento (vacío si no hay palabras de contexto). |
| `palabras_clave_contexto` | `str` | Palabras de contexto encontradas, unidas por `separador`. |
| `categorias_encontradas` | `set[str]` | Categorías con al menos un fragmento principal. |
| `categorias_faltantes` | `list[str]` | Categorías definidas sin ningún fragmento principal. |
| `tiene_coincidencias` | `bool` (propiedad) | `True` si hay fragmentos principales. |

**`Fragmento`** (inmutable): `palabra_clave`, `categoria`, `fragmento`, `posicion_inicio`, `posicion_fin` (span de la palabra clave), `inicio_fragmento`, `fin_fragmento` (span del fragmento), `palabra_reduccion`.

Ambos exponen `to_dict()` para serializar a JSON.

---

## 💻 Uso desde Línea de Comandos (CLI)

```bash
python -m extraccion_fragmento datos_entrada.csv -k palabras_clave.txt -r reduccion.txt
# equivalente (legacy):
python extraer_embargo.py datos_entrada.csv -k palabras_clave.txt -r reduccion.txt
```

Por defecto usa `palabras_clave.txt`, busca la columna `texto_limpio` (o `texto`), extrae 200 caracteres antes y después, y guarda los resultados en `output/fragmento_YYYY_MM_DD_HH_MM_SS/` (o con sufijo incremental `_1`, `_2` si se ejecutan múltiples procesos simultáneos).

### Ejemplos

```bash
# Ventana personalizada y archivo de salida
python -m extraccion_fragmento entrada.csv -a 300 -p 500 -o resultado.csv -c contenido_documento

# Caracteres por categoría (0:0 omite la categoría)
python -m extraccion_fragmento entrada.csv --chars-categoria "Datos_Embargado:200:300,Montos:50:100,Cuenta_depositar:0:0"

# Sin reducción ni agrupación
python -m extraccion_fragmento entrada.csv --sin-reduccion --sin-agrupar

# Completo
python -m extraccion_fragmento ../input_embargos_80.csv -c texto_limpio -k palabras_clave.txt -r reduccion.txt \
  --keywords-contexto palabras_contexto.txt -a 200 -p 300 --chars-categoria "Montos:50:100" -o output_embargos.csv
```

### Opciones

| Opción | Tipo | Default | Descripción |
| :--- | :--- | :--- | :--- |
| `input` | Posicional | _(requerido)_ | CSV de entrada. |
| `-o`, `--output` | `str` | `output_embargos.csv` | Nombre del CSV de salida principal. |
| `--output-dir` | `str` | `output` | Directorio base de las subcarpetas con timestamp. |
| `-c`, `--columna` | `str` | `texto_limpio` | Columna con el texto. |
| `-k`, `--keywords` | `str` | `palabras_clave.txt` | Archivo de palabras clave. |
| `-r`, `--reduccion` | `str` | `None` | Archivo de palabras de reducción. |
| `--extra` | `str` | `extra.csv` | Nombre del CSV de fragmentos reducidos. |
| `--sin-reduccion` | `flag` | `False` | Desactiva la reducción (`habilitar_reduccion=False`); no se genera el CSV extra. |
| `--sin-agrupar` | `flag` | `False` | Desactiva la agrupación (`habilitar_agrupacion=False`). |
| `-n`, `--nombre` | `str` | `None` | Valor fijo para `nombre` o nombre de la columna que lo contiene. |
| `--renumerar` | `flag` | `False` | `numero_archivo` siempre secuencial (1, 2, 3...). |
| `-a`, `--antes` | `int` | `200` | Caracteres antes (global). |
| `-p`, `--despues` | `int` | `200` | Caracteres después (global). |
| `--separador` | `str` | `' \| '` | Separador de palabras clave agrupadas. |
| `--chars-categoria` | `str` | `None` | `Cat1:antes:desp,Cat2:antes:desp`. |
| `--keywords-contexto` | `str` | `None` | Archivo de palabras clave para `contexto_embargado`. |
| `--antes-contexto` | `int` | `200` | Caracteres antes para `contexto_embargado`. |
| `--despues-contexto` | `int` | `200` | Caracteres después para `contexto_embargado`. |
| `--distancia-corte` | `int` | `0` | Máximo hacia adentro para buscar símbolo de corte (`0` desactiva). |
| `--simbolos-corte` | `str` | `""` | Símbolos de corte (ej. `','`, `',;.'`, `'.\n'`). |
| `--distancia-extension` | `int` | `0` | Máximo hacia afuera para buscar delimitadores (`0` = sin límite). |
| `--delimitadores-extension` | `str` | `""` | Delimitadores de extensión (ej. `'". ", \n'`; vacío desactiva). |

---

## 📝 Formato de Archivos

### Palabras clave (`palabras_clave.txt`, `palabras_contexto.txt`)

Texto plano `utf-8`, una palabra o frase por línea. Las líneas que empiezan con `--` definen la categoría de las siguientes. Se ignoran líneas vacías y las que empiezan con `#`.

```text
--Datos_Embargado--
dni
cuit
--Montos--
hasta cubrir la suma
```

### Reducción (`reduccion.txt`)

Texto plano `utf-8`, un término por línea (firmas de jueces, letrados, tomo/folio, etc.). Se normalizan y comparan como palabra completa sin distinguir mayúsculas, tildes ni puntos (`dr.` y `dr` funcionan de forma idéntica; `dr` no matchea dentro de `sandra`).

### CSV de entrada (modo CLI)

Delimitador `;`, `,` o tabulación (detección automática). Columnas detectadas:

- `numero_archivo`: si existe se respeta; si no, numeración secuencial desde 1.
- `id`: columna `id` o la primera columna.
- `nombre`: parametrizable con `-n` o columna `nombre`.
- Texto: `-c`, con fallback a `texto_limpio` / `texto`.

### CSV de salida principal (`output_embargos.csv`)

Codificación `utf-8-sig`, delimitador `;`.

| Columna | Descripción |
| :--- | :--- |
| `numero_archivo` | Del CSV original o secuencial. |
| `id` | Identificador del documento. |
| `nombre` | Valor de `-n` o de la columna `nombre`. |
| `contador_interno` | Índice del fragmento en el documento (1, 2, 3...) o `0` si no hubo fragmentos. |
| `palabra_clave` | Palabra(s) clave que originaron el fragmento. |
| `categoria` | Categoría de la palabra clave. |
| `fragmento` | Texto extraído. |
| `contexto_embargado` | Contexto del documento según `--keywords-contexto`. |
| `palabra_clave_contexto` | Palabras de contexto encontradas. |
| `posicion_inicio` / `posicion_fin` | Span de la palabra clave en el texto original. |
| `inicio_fragmento` / `fin_fragmento` | Span del fragmento en el texto original. |
| `texto_completo` | Texto original del documento. |

> [!NOTE]
> Para preservar el 100% de los documentos y la correspondencia `(numero_archivo, id)`, los documentos sin fragmentos se incluyen con `contador_interno = 0` y campos de fragmento vacíos.

### CSV de salida extra (`extra.csv`)

Solo cuando la reducción está habilitada. Mismas columnas que el principal (sin las de contexto) más `palabra_reduccion` con el motivo. También incluye una fila con `contador_interno = 0` para los documentos sin fragmentos reducidos.

### Reporte de categorías faltantes (`<salida>_sin_match.txt`)

TSV con `numero_archivo`, `id` y una columna `SI`/`NO` por categoría, solo para documentos con al menos una categoría faltante.

---

## 🧪 Tests

```bash
python -m unittest discover -s tests -v
```
