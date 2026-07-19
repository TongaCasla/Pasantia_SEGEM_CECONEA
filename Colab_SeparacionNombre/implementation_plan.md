# Plan de Implementación: Script Colab con GLiNER2

El objetivo es crear un script de Python en el directorio `Colab_SeparacionNombre` que realice el mismo procesamiento y agrupación jerárquica de documentos del script anterior, pero que en lugar de usar un LLM local a través de LM Studio, utilice el modelo zero-shot de reconocimiento de entidades **`fastino/gliner2-privacy-filter-PII-multi`** mediante la librería `gliner2`.

Este script se ejecutará en Google Colab con el archivo CSV de entrada y el JSON de salida pasados por argumentos de consola (`-i` / `--input` y `-o` / `--output`).

## Cambios Propuestos

### Componente: Scripts para Colab

#### [NEW] [separacion_nombres_colab.py](file:///c:/Users/tonga/OneDrive/Escritorio/BD_supervisada/Scripts/Colab_SeparacionNombre/separacion_nombres_colab.py)
Crear un nuevo script de Python que contenga:
1. **Instrucciones para Colab**: Un bloque de comentarios al inicio del archivo con los comandos `pip` necesarios para ejecutar el script en Google Colab.
2. **Carga y Configuración del Modelo**:
   - Detectar si CUDA está disponible en PyTorch para ejecutar el modelo en la GPU de Colab de forma ultra-rápida.
   - Cargar el modelo `fastino/gliner2-privacy-filter-PII-multi` usando la clase `GLiNER2` de la librería `gliner2`.
3. **Mapeo de Entidades (GLiNER2)**:
   - Extraer las etiquetas `["first_name", "middle_name", "last_name"]`.
   - Agrupar `first_name` y `middle_name` en el campo `nombre`.
   - Agrupar `last_name` en el campo `apellido`.
   - Si no se detectan entidades o hay ambigüedad, aplicar el fallback por defecto (`nombre = ""`, `apellido = <nombre original>`).
4. **Procesamiento por Lotes y Fallbacks**:
   - Dividir la lista de nombres únicos a procesar en lotes de tamaño configurable (por defecto `32`).
   - Intentar procesar en lote para maximizar el uso de GPU.
   - Implementar un fallback secuencial (uno a uno) si el procesamiento por lotes falla o devuelve resultados inesperados.
5. **Caché Local**:
   - Mantener la persistencia en caché mediante un archivo JSON (por defecto `_cache_nombres.json`) para evitar reprocesar nombres ya separados.
6. **Argumentos de Consola**:
   - `-i` / `--input` (Requerido): Ruta al CSV de entrada.
   - `-o` / `--output` (Requerido): Ruta al JSON de salida.
   - `--model` (Opcional): Nombre del modelo a cargar (default: `fastino/gliner2-privacy-filter-PII-multi`).
   - `--batch-size` (Opcional): Tamaño del lote (default: `32`).
   - `--cache` (Opcional): Archivo de caché de nombres (default: `_cache_nombres.json`).
   - `--threshold` (Opcional): Umbral de confianza de predicción (default: `0.4`).

---

## Plan de Verificación

Dado que este script utiliza PyTorch y la biblioteca `gliner2` (que requiere recursos específicos de hardware y dependencias), la verificación del funcionamiento completo del modelo se realizará directamente en Google Colab.

### Pruebas de Sintaxis y Argumentos en Local
Ejecutar validaciones básicas locales (sin GPU) para garantizar que la estructura del script de Python no contenga errores de sintaxis y que el parseo de argumentos sea correcto:
```bash
python c:\Users\tonga\OneDrive\Escritorio\BD_supervisada\Scripts\Colab_SeparacionNombre\separacion_nombres_colab.py --help
```

### Verificación en Colab
El usuario podrá subir el script a GitHub y ejecutarlo en Colab con los siguientes comandos:
```bash
!pip install gliner2 torch
!python separacion_nombres_colab.py -i input.csv -o output.json
```
Se comprobará que:
1. El modelo se descargue y se cargue en la GPU (si está activa).
2. Se procese correctamente el archivo CSV y se agrupen los datos jerárquicamente por documento.
3. Se separen los nombres en el objeto `{"nombre": "...", "apellido": "..."}` para la etiqueta `persona`.
4. Se cree/actualice la caché en `_cache_nombres.json`.
