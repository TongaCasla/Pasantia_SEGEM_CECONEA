# Suite de Pruebas Unitarias (`tests/`)

Este directorio contiene las pruebas automatizadas del paquete `extraccion_fragmento`. La suite valida la integridad del motor de extracción en memoria, sus filtros configurables y la robustez del CLI.

---

## 🚀 Ejecución de Pruebas

Para ejecutar la suite completa utilizando el módulo `unittest` de la librería estándar de Python:

```bash
# Ejecución estándar con detalle (verbose)
python -m unittest discover -s tests -v

# Ejecución de un archivo de pruebas específico
python -m unittest tests/test_extractor.py -v

# Ejecución de un caso de prueba puntual
python -m unittest tests.test_extractor.ExtraccionFragmentoTest.test_cuil_sin_numero_se_reduce
```

---

## 📋 Cobertura y Casos de Prueba (`test_extractor.py`)

La clase `ExtraccionFragmentoTest` cubre las siguientes áreas funcionales:

### 1. Extracción e Integridad en Memoria
* **`test_extrae_en_memoria_y_devuelve_resultado_tipado`**: Verifica que `extractor.extraer()` retorne una instancia de `ResultadoExtraccion` con `Fragmento`s válidos y comprueba que el span `texto[inicio:fin]` coincida exactamente con `fragmento`.
* **`test_normaliza_tildes_y_puntos`**: Valida que la normalización NFD permita encontrar términos como `D.N.I.` a partir de la keyword `dni` sin modificar el texto original extraído.
* **`test_texto_vacio`**: Comprueba que textos vacíos o nulos no generen excepciones y retornen un resultado vacío con las categorías faltantes intactas.
* **`test_extraer_lote`**: Valida que `extractor.extraer_lote()` funcione como generador streaming y procese correctamente listas con documentos válidos, vacíos o `None`.

### 2. Filtro de Reducción de Falsos Positivos (Ítem 4)
* **`test_reduccion_habilitada_separa_dni_sin_numero`**: Comprueba que menciones de documentos (DNI) sin números posteriores se desvíen a `fragmentos_reducidos` con motivo `"sin_numero"`.
* **`test_cuil_sin_numero_se_reduce`**: Valida específicamente que la clave `cuil` sin dígitos asociados active correctamente la reducción lógica `"sin_numero"`.
* **`test_reduccion_con_puntos_dr_y_dra`**: Valida que patrones con puntos (`dr.`, `dra.`) se normalicen correctamente y detecten firmas o menciones de letrados (`"Dr. Gómez"`).
* **`test_reduccion_por_patrones`**: Comprueba el filtrado por palabras clave externas (`palabras_reduccion=["juez"]`) hacia `fragmentos_reducidos`.
* **`test_reduccion_deshabilitada_no_reduce_nada`**: Comprueba que al configurar `habilitar_reduccion=False`, ningún fragmento sea filtrado, conservando todos en la salida principal.

### 3. Fusión de Intervalos Superpuestos (Ítem 5)
* **`test_agrupacion_fusiona_superpuestos_de_misma_categoria`**: Verifica que múltiples coincidencias continuas o solapadas de la misma categoría se consoliden en un único fragmento continuo separado por `" | "`. Compara el conteo contra `habilitar_agrupacion=False`.

### 4. Configuración y Casos de Borde
* **`test_categoria_cero_cero_se_omite`**: Valida que categorías configuradas con ventana `(0, 0)` en `chars_por_categoria` sean omitidas de la extracción y figuren en `categorias_faltantes`.
* **`test_config_invalida`**: Comprueba que valores negativos en ventanas o listas vacías de palabras clave lancen `ValueError`.
* **`test_contexto`**: Valida la extracción de backup global `contexto_embargado` y la concatenación de `palabras_clave_contexto`.

### 5. Adaptador CLI y Manejo de Concurrencia
* **`test_generar_carpeta_ejecucion_evita_colisiones`**: Verifica que la función `generar_carpeta_ejecucion` cree carpetas únicas con sufijo incremental cuando dos ejecuciones ocurren dentro del mismo segundo en un entorno de producción.

---

## 🛠️ Pautas para Agregar Nuevos Tests

1. **Cero Dependencias**: Los tests deben usar exclusivamente `unittest` y la librería estándar (sin requerir `pytest` ni paquetes de terceros obligatorios).
2. **Aislamiento**: Cada test debe ser idempotente y no depender del estado de tests anteriores.
3. **Archivos Temporales**: Si un test necesita interactuar con el sistema de archivos (ej. testing de CLI o carpetas), utilizar `tempfile.TemporaryDirectory()` dentro de un bloque `with`.
