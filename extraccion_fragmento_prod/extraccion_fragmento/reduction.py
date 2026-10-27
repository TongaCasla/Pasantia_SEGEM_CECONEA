"""
False-positive reduction (optional stage, toggled by
``ExtractorConfig.habilitar_reduccion``).

A match is "reduced" (moved out of the main output) when it belongs to the
reducible category and either:
  1. its keyword requires a number (e.g. DNI/CUIT) and no digit follows it
     inside the fragment -> reason ``"sin_numero"``, or
  2. the normalized fragment matches one of the reduction patterns -> reason
     is the original reduction word.
"""
import re
import unicodedata

from .normalizer import normalizar_nombre_categoria, normalizar_palabra, normalizar_texto

MOTIVO_SIN_NUMERO = "sin_numero"


def preparar_patrones_reduccion(palabras_reduccion):
    """
    Prepara expresiones regulares para las palabras/frases de reducción.
    Aplica normalización (sin acentos, minúsculas, sin puntos) y límites de palabra
    adecuados para evitar falsos positivos (e.g. 'dr' dentro de 'sandra').
    """
    patrones = []
    patrones_vistos = set()
    for palabra in palabras_reduccion:
        palabra_orig = palabra.strip()
        palabra_norm = normalizar_palabra(palabra_orig)
        if not palabra_norm:
            continue
        if palabra_norm in patrones_vistos:
            continue
        patrones_vistos.add(palabra_norm)
        prefix = r'(?<!\w)' if re.match(r'^\w', palabra_norm) else ''
        suffix = r'(?!\w)' if re.search(r'\w$', palabra_norm) else ''
        pattern = re.compile(prefix + re.escape(palabra_norm) + suffix, re.IGNORECASE)
        patrones.append({
            'palabra_original': palabra_orig,
            'pattern': pattern
        })
    return patrones


def es_categoria_reducible(categoria, categoria_reduccion):
    """True when the category (normalized) starts with the reducible category."""
    if not categoria or not categoria_reduccion:
        return False
    return normalizar_nombre_categoria(categoria).startswith(categoria_reduccion)


def evaluar_reduccion(texto, match, fragmento, fin_frag, patrones, categoria_reduccion, claves_requieren_numero):
    """
    Returns the reduction reason for a match, or ``None`` if it must stay in
    the main output.
    """
    if not es_categoria_reducible(match['categoria'], categoria_reduccion):
        return None

    # 1. Reducción lógica: la palabra clave exige un número a continuación
    if claves_requieren_numero:
        p_clave_norm, _ = normalizar_texto(match['palabra_clave'])
        if any(k in p_clave_norm for k in claves_requieren_numero):
            texto_hacia_adelante = texto[match['fin']:fin_frag]
            if not any(c.isdigit() for c in texto_hacia_adelante):
                return MOTIVO_SIN_NUMERO

    # 2. Reducción por patrones (ej. reduccion.txt)
    if patrones:
        norm_frag, _ = normalizar_texto(fragmento)
        for pat in patrones:
            if pat['pattern'].search(norm_frag):
                return pat['palabra_original']

    return None
