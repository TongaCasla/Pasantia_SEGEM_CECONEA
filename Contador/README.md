# ✦ Contador de Caracteres

Una aplicación web moderna y liviana para calcular la cantidad de caracteres, palabras y líneas de cualquier texto en tiempo real. 

El backend está desarrollado con **Python (Flask)** y el frontend utiliza **HTML, CSS y JavaScript** puro con un diseño *glassmorphic*.

---

## 🚀 Características

- **Conteo en tiempo real:** Actualización dinámica mientras escribís o pegás texto.
- **Métricas completas:**
  - Caracteres totales (con espacios)
  - Caracteres sin espacios
  - Cantidad de palabras
  - Cantidad de líneas
- **Diseño moderno:** Interfaz oscura, elegante y responsive con animaciones fluidas.

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
├── app.py              # Servidor Flask y API REST (/api/count)
├── requirements.txt    # Dependencias de Python (Flask)
├── README.md           # Documentación del proyecto
└── static/
    └── index.html      # Interfaz de usuario (HTML + CSS + JS)
```
