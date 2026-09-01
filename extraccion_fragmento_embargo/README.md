# Extracción de Fragmentos de Embargos

Herramienta en Python para la búsqueda y extracción de fragmentos de texto en documentos legales de embargos desde archivos CSV.

El script identifica coincidencia de palabras o frases clave (insensible a mayúsculas y acentos) y extrae una ventana parametrizable de caracteres antes y después de cada coincidencia para facilitar la identificación de datos relevantes (datos del embargado, montos, cuentas a depositar, etc.).

---

## 🚀 Características

- **Búsqueda insensible a mayúsculas y acentos**: Utiliza normalización NFD (`unicodedata`) para emparejar palabras clave ignorando diacríticos y capitalización, sin alterar el texto original extraído.
- **Mapeo exacto de posiciones**: Correlaciona los índices del texto normalizado con el texto original para preservar la integridad del fragmento extraído.
- **Contexto configurable**: Permite definir la cantidad exacta de caracteres a extraer antes (`-a`) y después (`-p`) de la palabra clave.
- **Detección automática de delimitadores**: Soporta CSVs delimitados por punto y coma (`;`), coma (`,`) o tabulación (`\t`).
- **Soporte de comentarios en palabras clave**: Archivo plano de palabras clave editable, donde se pueden omitir líneas o agregar comentarios mediante `#`.
- **Cero dependencias externas**: Requiere exclusivamente módulos de la librería estándar de Python.

---

## 📋 Requisitos

- **Python**: Version 3.7 o superior.
- Sin dependencias de paquetes de terceros (`pip`).

---

## 📂 Estructura del Proyecto

```text
extraccion_embargo/
│
├── extraer_embargo.py      # Script principal CLI
├── palabras_clave.txt      # Listado editable de frases/palabras clave a buscar
├── prompt.txt              # Requerimientos e instrucciones de origen
└── output_embargos.csv     # CSV generado por el script con los fragmentos encontrados
```

---

## 💻 Uso de la Línea de Comandos (CLI)

### Comando Básico

```bash
python extraer_embargo.py datos_entrada.csv
```

Por defecto:

- Utilizará `palabras_clave.txt` como origen de palabras clave.
- Buscará en la columna llamada `texto_limpio` (o `texto` como alternativa).
- Extraerá **200 caracteres antes** y **200 caracteres después** de la coincidencia.
- Guardará el resultado en `output_embargos.csv`.

### Ejemplo Completo

Ejemplo de ejecución combinando todos los parámetros personalizados (archivo de entrada `../input_embargos_80.csv`, columna `texto_limpio`, palabras clave `palabras_clave.txt`, 200 caracteres antes y 300 después):

```bash
python extraer_embargo.py ../input_embargos_80.csv -c texto_limpio -k palabras_clave.txt -a 200 -p 300 -o output_embargos.csv
```

---

### Ejemplos Avanzados

1. **Especificar un archivo de salida y una columna personalizada:**

   ```bash
   python extraer_embargo.py entrada.csv -o resultado.csv -c contenido_documento
   ```

2. **Ajustar la ventana de contexto (ej. 300 caracteres antes y 500 después):**

   ```bash
   python extraer_embargo.py entrada.csv -a 300 -p 500
   ```

3. **Usar un archivo de palabras clave personalizado:**
   ```bash
   python extraer_embargo.py entrada.csv -k mis_palabras.txt
   ```
4. **Ejemplo completo**
   ```bash
   python extraer_embargo.py ../input_embargos_80.csv -c texto_limpio -k palabras_clave.txt -a 200 -p 300 -o output_embargos.csv
   ```

---

## ⚙️ Parámetros y Opciones

| Argumento / Opción | Tipo       | Valor por defecto     | Descripción                                                |
| :----------------- | :--------- | :-------------------- | :--------------------------------------------------------- |
| `input`            | Posicional | _(Requerido)_         | Ruta al archivo CSV de entrada.                            |
| `-o`, `--output`   | `str`      | `output_embargos.csv` | Ruta al archivo CSV de salida.                             |
| `-c`, `--columna`  | `str`      | `texto_limpio`        | Nombre de la columna en el CSV que contiene el texto.      |
| `-k`, `--keywords` | `str`      | `palabras_clave.txt`  | Ruta al archivo de texto con las palabras clave.           |
| `-a`, `--antes`    | `int`      | `200`                 | Número de caracteres a extraer antes de la coincidencia.   |
| `-p`, `--despues`  | `int`      | `200`                 | Número de caracteres a extraer después de la coincidencia. |

---

## 📝 Formato de Archivos

### 1. Archivo de Palabras Clave (`palabras_clave.txt`)

Archivo de texto plano (`utf-8`) con una palabra o frase clave por línea. Se ignoran líneas en blanco y comentarios que comiencen con `#`.

```text
# Frases de decretos de embargo
decretase embargo sobre
proceda al embargo
embargo preventivo

# Frases de transferencia/fondos
transferir dichos fondos
remita el saldo
hasta cubrir la suma
```

### 2. CSV de Entrada

El archivo CSV debe incluir al menos las siguientes columnas (el script las detecta de forma insensible a mayúsculas):

- `numero_archivo` (opcional, default col 0)
- `id` (opcional, default col 1)
- `nombre` (opcional, default col 2)
- Columna de texto (configurable con `-c`, por defecto `texto_limpio`).

### 3. CSV de Salida (`output_embargos.csv`)

Generado con codificación `utf-8-sig` y delimitador `;`. Incluye las siguientes columnas:

| Columna            | Descripción                                                       |
| :----------------- | :---------------------------------------------------------------- |
| `numero_archivo`   | Número de archivo proveniente del CSV original.                   |
| `id`               | Identificador del documento del CSV original.                     |
| `nombre`           | Nombre del documento original.                                    |
| `contador_interno` | Índice secuencial de coincidencia para el documento (1, 2, 3...). |
| `palabra_clave`    | Palabra o frase clave que originó el match.                       |
| `fragmento`        | Substring del texto extraído alrededor de la palabra clave.       |
| `posicion_inicio`  | Índice de inicio de la palabra clave en el texto original.        |
| `posicion_fin`     | Índice de fin de la palabra clave en el texto original.           |
| `inicio_fragmento` | Índice global de inicio de la ventana de fragmento.               |
| `fin_fragmento`    | Índice global de fin de la ventana de fragmento.                  |

---

## 📊 Resumen de Ejecución

Al finalizar el proceso, la herramienta imprime en consola un resumen técnico:

```text
--- Resumen de ejecución ---
Documentos procesados: 85
Documentos con coincidencias: 62
Registros de fragmentos generados: 148
Archivo de salida guardado en: 'output_embargos.csv'
```
