# Guía de Comandos Git para Subir el Código

Esta guía detalla los comandos Git necesarios para subir los archivos de extracción de entidades GLiNER a tu repositorio de GitHub.

Dado que el repositorio raíz es `Pasantia_SEGEM_CECONEA` y los archivos modificados están dentro de la carpeta `ExtraccionGLiner`, puedes seguir estos pasos.

---

## 1. Consultar el estado actual
Para verificar qué archivos han sido modificados o agregados:
```bash
git status
```

---

## 2. Agregar los archivos al área de preparación (Staging)

Puedes agregar específicamente los archivos del proyecto para evitar subir archivos temporales:
```bash
git add ExtraccionGLiner/requirements.txt ExtraccionGLiner/extraccion_gliner.py ExtraccionGLiner/README.md
```
*(O si prefieres agregar todos los cambios de la carpeta actual)*:
```bash
git add ExtraccionGLiner/
```
*(O agregar absolutamente todos los cambios del repositorio)*:
```bash
git add .
```

---

## 3. Crear el Commit
Guarda los cambios localmente con un mensaje descriptivo:
```bash
git commit -m "feat: implementar script de extracción GLiNER con soporte JSON/CSV y chunking"
```

---

## 4. Obtener cambios remotos (Pull)
Antes de subir tu código, siempre es recomendable traer los últimos cambios del repositorio remoto para evitar conflictos:
```bash
git pull origin main
```

---

## 5. Subir los cambios a GitHub (Push)
Envía tus commits locales a la rama `main` de tu repositorio remoto:
```bash
git push origin main
```

---

## Resumen de flujo rápido
Si no hay cambios pendientes de otros lados y quieres subir todo directamente:
```bash
git add ExtraccionGLiner/
git commit -m "feat: implementar script de extracción GLiNER"
git pull origin main
git push origin main
```
