"""
Text normalization and keyword matching.

Normalization is NFD-based (diacritics removed, dots removed, lowercase) and
keeps an index map back to the original text, so extracted fragments always
come from the untouched original string.
"""
import re
import unicodedata

_CHARS_ELIMINAR = {'.'}


def normalizar_nombre_categoria(categoria):
    """Normalizes a category name for comparisons: lowercase, spaces -> '_'."""
    return categoria.strip().lower().replace(' ', '_')


def _normalizar_char_a_chars(char):
    """
    Normaliza un carácter: descompone NFD, elimina diacríticos,
    elimina puntos (.), y pasa a minúsculas.
    Retorna lista de caracteres resultantes (puede ser vacía si se elimina).
    """
    resultado = []
    nfd = unicodedata.normalize('NFD', char)
    for c in nfd:
        if unicodedata.category(c) != 'Mn' and c not in _CHARS_ELIMINAR:
            resultado.append(c.lower())
    return resultado


def normalizar_palabra(palabra):
    """Normalizes a keyword with the same rules applied to the text."""
    return "".join(c for char in palabra for c in _normalizar_char_a_chars(char))


def normalizar_texto(texto):
    """
    Normaliza el texto: convierte a minúsculas, elimina acentos/diacríticos
    y elimina puntos (.).
    Retorna el texto normalizado y una lista que mapea cada índice del texto
    normalizado al índice correspondiente en el texto original.
    """
    if not texto:
        return "", []

    norm_chars = []
    orig_indices = []

    for idx, char in enumerate(texto):
        for c in _normalizar_char_a_chars(char):
            norm_chars.append(c)
            orig_indices.append(idx)

    orig_indices.append(len(texto))
    return "".join(norm_chars), orig_indices


def buscar_palabras_clave(texto_original, palabras_clave):
    """
    Busca las palabras clave en el texto original (normalizando ambos).
    Retorna una lista de diccionarios con la información de las coincidencias.
    Cada elemento de palabras_clave es un dict con 'palabra' y 'categoria'.
    """
    if not texto_original or not palabras_clave:
        return []

    norm_text, orig_indices = normalizar_texto(texto_original)
    coincidencias = []

    for entrada in palabras_clave:
        palabra_limpia = entrada['palabra'].strip()
        categoria = entrada['categoria']
        if not palabra_limpia:
            continue

        palabra_norm = normalizar_palabra(palabra_limpia)
        if not palabra_norm:
            continue

        pattern = re.compile(re.escape(palabra_norm))
        for match in pattern.finditer(norm_text):
            norm_start = match.start()
            norm_end = match.end()

            orig_start = orig_indices[norm_start]
            orig_end = orig_indices[norm_end] if norm_end < len(orig_indices) else len(texto_original)

            coincidencias.append({
                'palabra_clave': palabra_limpia,
                'categoria': categoria,
                'inicio': orig_start,
                'fin': orig_end,
                'texto_matcheado': texto_original[orig_start:orig_end]
            })

    # Ordenar coincidencias por posición de inicio en el texto original
    coincidencias.sort(key=lambda x: x['inicio'])
    return coincidencias
