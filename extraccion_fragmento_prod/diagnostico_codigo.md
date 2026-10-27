# Diagnóstico y Análisis del Código (`extraer_embargo.py`)

Este documento consolida el relevamiento técnico del script original previo a la refactorización para producción.

---

## 1. Responsabilidades Actuales del Código

El script resuelve un problema de extracción de información no estructurada sobre documentos legales (embargos) a partir de coincidencias léxicas, ventanas contextuales y filtros de calidad. Se compone de 6 bloques funcionales:

### 1. Ingesta y Parsing de Configuración
* **Funciones:**
  * `cargar_palabras_clave(ruta_archivo)`: Carga listas de palabras clave con categorías (`--Categoria--`).
  * `cargar_palabras_reduccion(ruta_archivo)`: Carga frases o términos que indican falsos positivos.
  * `parsear_chars_categoria(cadena_config)`: Interpreta ventanas específicas por categoría (`Categoria:antes:despues`).
  * `parsear_simbolos_corte(cadena)`: Interpreta caracteres o secuencias de corte para bordes de fragmento.
  * `parsear_delimitadores_extension(cadena)`: Interpreta delimitadores semánticos (`. `, `\n`, etc.) para extender oraciones completas.
* **Rol:** Lee archivos de texto planos y parsea cadenas de configuración desde CLI/texto.

### 2. Motor de Normalización y Búsqueda (Core Matching)
* **Funciones:**
  * `_normalizar_char_a_chars(char)`: Normalización individual NFD (remueve diacríticos, puntos y minúsculas).
  * `normalizar_texto(texto)`: Normaliza el texto completo y genera un mapa de índices (`orig_indices`).
  * `buscar_palabras_clave(texto_original, palabras_clave)`: Busca palabras clave en el texto normalizado y mapea los spans al texto original.
* **Rol:** Garantiza búsqueda insensible a mayúsculas, tildes y puntos, manteniendo la integridad posicional exacta sobre el texto original sin alterar su formato.

### 3. Delimitación y Ajuste de Ventanas (Boundary & Slicing)
* **Funciones:**
  * `extender_limites_fragmento(...)`: Expande los límites del fragmento hacia delimitadores semánticos naturales.
  * `ajustar_limites_palabra(...)`: Ajusta límites para no cortar palabras por la mitad o recortar en símbolos de puntuación.
  * `extraer_fragmento(...)`: Orquesta la extracción de la ventana y sus ajustes.
* **Rol:** Define los bordes de cada fragmento extrayendo oraciones o párrafos coherentes alrededor del match.

### 4. Lógica de Reducción y Falsos Positivos
* **Funciones:**
  * `preparar_patrones_reduccion(palabras_reduccion)`: Compila regexes con boundaries (`\b`) para evitar falsos matches.
  * Reglas inline en el procesador (ej: validación de presencia de números tras términos como DNI/CUIT).
* **Rol:** Detecta menciones que no constituyen un dato útil y las deriva a una salida secundaria (`extra.csv`).

### 5. Consolidación de Intervalos (Merging)
* **Funciones:**
  * `agrupar_fragmentos_superpuestos(matches, texto, separador)`: Fusiona ventanas superpuestas o contiguas dentro de la misma categoría.
  * `extraer_contexto_embargado(...)`: Extrae párrafos de contexto global del documento fusionando intervalos superpuestos.
* **Rol:** Evita duplicación y fragmentación innecesaria consolidando información contigua en un solo párrafo continuo.

### 6. Orquestador Monolítico y CLI
* **Funciones:**
  * `procesar_csv(...)`: Función monolítica de más de 450 líneas que maneja la I/O de CSVs, detección de dialectos, mapeo de columnas, loops, métricas y guardado de resultados.
  * `main()`: Parser de argumentos CLI (`argparse`).
  * `desescapar_texto(...)`: Limpieza de caracteres escapados de CSV.
  * `buscar_indice_columna(...)`: Detección flexible de encabezados.

---

## 2. Puntos Críticos para Producción

1. **Acoplamiento Fuerte con el Sistema de Archivos y CSV:** La lógica de extracción está entremezclada con `csv.reader`, `open()`, rutas de archivos y creación de carpetas con timestamp.
2. **Imposibilidad de Uso en Memoria (Black Box):** No existe una interfaz simple que reciba un `str` (o lista de strings) y devuelva objetos estructurados.
3. **Rigidez de Procesos:** La reducción de falsos positivos (Ítem 4) y la agrupación de fragmentos superpuestos (Ítem 5) deben ser configurables mediante flags booleanos o estrategias intercambiables.
4. **Falta de Abstracción en Configuración:** Existen más de 20 parámetros sueltos en lugar de un objeto de configuración tipado (`Config`).
