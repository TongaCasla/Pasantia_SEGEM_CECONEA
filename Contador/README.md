# ✦ Contador y Visualizador de Spans

Una aplicación web moderna, liviana y potente para contar métricas de texto en tiempo real, buscar apariciones con precisión de caracteres y visualizar anotaciones de entidades (spans) desde archivos CSV (compatible con GLiNER y anotadores de NLP).

El backend está desarrollado con **Python (Flask)** y el frontend utiliza **HTML5, CSS3 y JavaScript** puro con una interfaz *dark glassmorphic*.

---

## 🚀 Características Principales

La aplicación cuenta con dos pestañas orientadas a distintas necesidades de análisis de texto:

### 📊 1. Contador & Búsqueda de Spans
- **Conteo en Tiempo Real:** Métricas instantáneas al escribir o pegar texto.
  - Caracteres totales (con espacios)
  - Caracteres sin espacios
  - Cantidad de palabras
  - Cantidad de líneas
- **Búsqueda de Spans con Offsets Precisos:**
  - Búsqueda insensible a mayúsculas/minúsculas y acentos.
  - Mapeo exacto de posiciones `Start` y `End` en el texto original, previniendo desfases causados por normalizaciones o caracteres acentuados.
  - Resaltado visual interactivo sincronizado con el desplazamiento (scroll) del texto.
- **Modo GLiNER:** Opción para desescapar comillas dobles internas provenientes de exportaciones CSV (`"" → "`)...

### 🏷️ 2. Visualizador de Spans (CSV)
- **Soporte de Estructura CSV:** Compatible con el formato `id,texto_limpio,etiqueta,valor,span_inicio,span_fin` (o `spawn_inicio`).
- **Carga Flexible:** Soporta arrastrar y soltar (Drag & Drop), selección de archivo (`.csv`, `.txt`) o pegado directo de datos.
- **Detección Automática de Delimitadores & BOM:** Procesa archivos con coma (`,`), punto y coma (`;`) o tabulaciones (`\t`), eliminando marcas de orden de bytes UTF-8 (`\ufeff`).
- **Desplegable Numerado por Documento (ID):** Permite procesar CSVs con múltiples documentos (ej: `1. 3456`, `2. 7890`), cargando automáticamente su `texto_limpio` y sus spans correspondientes al seleccionar un ID.
- **Resaltado Multi-Color por Etiqueta:** Asignación dinámica de paletas de colores únicas para cada categoría de entidad (PER, ORG, LOC, etc.).
- **Leyenda Interactiva:** Muestra las etiquetas presentes con sus respectivos colores asignados.
- **Buscador Independiente (Cian Eléctrico):**
  - Permite buscar textos específicos dentro del documento seleccionado.
  - Resaltado distintivo en cian eléctrico con borde y resplandor luminoso para no confundirse con las etiquetas de entidades.
  - Soporta superposición: si una palabra buscada posee una etiqueta de entidad, preserva el fondo de la etiqueta y añade el contorno cian.
- **Tabla de Spans Resaltados:** Muestra una lista con número de fila, etiqueta, valor del CSV, posiciones y estado de coincidencia (`✓ Exacto` / `⚠ Parcial`).
- **Tabla de Spans No Encontrados o Manuales:** Sección que alerta sobre aquellas etiquetas ingresadas manualmente que no poseen coordenadas o quedan fuera del texto.

---

## 🛠️ Requisitos Previos

- **Python 3.8+** instalado.

---

## 📦 Instalación

1. Clona o descarga este repositorio en tu equipo.
2. Abre una terminal en la carpeta del proyecto.
3. Instala las dependencias necesarias:

```bash
pip install -r requirements.txt
```

---

## ⚡ Ejecución

Para iniciar el servidor de desarrollo, ejecuta:

```bash
python app.py
```

Luego abre tu navegador e ingresa a:

👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 📁 Estructura del Proyecto

```text
Contador/
├── app.py              # Backend Flask (API /api/count y /api/parse-csv)
├── requirements.txt    # Dependencias de Python (Flask)
├── README.md           # Documentación del proyecto
└── static/
    └── index.html      # Interfaz de usuario completa (HTML + CSS + JS)
```
