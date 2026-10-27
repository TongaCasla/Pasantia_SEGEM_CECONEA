"""
Loaders for plain-text configuration files (keywords, reduction words).
These are the only core helpers that touch the file system.
"""
import os


def cargar_palabras_clave(ruta_archivo):
    """
    Carga palabras clave desde un archivo de texto, una por línea.
    Ignora líneas vacías y comentarios que comiencen con '#'.

    Las líneas que comienzan con '--' se interpretan como
    encabezados de categoría (e.g. '--Datos_Embargado--').
    Retorna una lista de diccionarios: [{'palabra': str, 'categoria': str}].
    Lanza FileNotFoundError si el archivo no existe.
    """
    if not ruta_archivo or not os.path.exists(ruta_archivo):
        raise FileNotFoundError(f"El archivo de palabras clave '{ruta_archivo}' no existe.")

    palabras = []
    categoria_actual = 'sin_categoria'

    with open(ruta_archivo, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line_cleaned = line.strip()
            if not line_cleaned or line_cleaned.startswith('#'):
                continue

            # Detectar encabezados de categoría: líneas que comienzan con '--'
            if line_cleaned.startswith('--'):
                # Extraer nombre de categoría removiendo guiones de ambos lados
                categoria_actual = line_cleaned.strip('-').strip()
                continue

            palabras.append({
                'palabra': line_cleaned,
                'categoria': categoria_actual
            })
    return palabras


def cargar_palabras_reduccion(ruta_archivo):
    """
    Carga palabras o frases de reducción desde un archivo de texto, una por línea.
    Ignora líneas vacías y comentarios que comiencen con '#'.
    Retorna una lista de strings limpios.
    Lanza FileNotFoundError si el archivo no existe.
    """
    if not ruta_archivo or not os.path.exists(ruta_archivo):
        raise FileNotFoundError(f"El archivo de reducción '{ruta_archivo}' no existe.")

    palabras = []
    with open(ruta_archivo, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line_cleaned = line.strip()
            if not line_cleaned or line_cleaned.startswith('#'):
                continue
            palabras.append(line_cleaned)
    return palabras
