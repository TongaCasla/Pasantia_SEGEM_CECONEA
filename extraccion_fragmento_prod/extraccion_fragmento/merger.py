"""
Interval merging.

- ``agrupar_fragmentos_superpuestos``: optional stage (toggled by
  ``ExtractorConfig.habilitar_agrupacion``) that merges overlapping fragments
  of the same category into a single paragraph.
- ``extraer_contexto_embargado``: document-level context built from context
  keywords; overlapping windows are always merged.
"""
from .normalizer import buscar_palabras_clave
from .window import extraer_fragmento


def fusionar_intervalos(intervalos):
    """
    Merges overlapping or adjacent ``(inicio, fin)`` intervals.
    Returns the merged intervals sorted by position.
    """
    if not intervalos:
        return []
    ordenados = sorted(intervalos, key=lambda v: (v[0], v[1]))
    grupos = []
    inicio_act, fin_act = ordenados[0]
    for ini, fin in ordenados[1:]:
        if ini <= fin_act:
            # Hay solapamiento o continuidad: expandir ventana
            fin_act = max(fin_act, fin)
        else:
            # Cerrar grupo actual y empezar nuevo grupo
            grupos.append((inicio_act, fin_act))
            inicio_act, fin_act = ini, fin
    grupos.append((inicio_act, fin_act))
    return grupos


def agrupar_fragmentos_superpuestos(matches, texto, separador=" | "):
    """
    Agrupa coincidencias cuyos spans de fragmento [inicio_frag, fin_frag]
    se superponen o son adyacentes (inicio_frag <= fin_anterior), únicamente
    si pertenecen a la MISMA categoría.

    Retorna una lista de diccionarios de párrafos consolidados, ordenada
    globalmente por posición de inicio en el texto.
    """
    if not matches:
        return []

    # Agrupar matches por categoría para fusionar únicamente los de la misma categoría
    matches_por_categoria = {}
    for m in matches:
        cat = m.get('categoria', 'sin_categoria')
        matches_por_categoria.setdefault(cat, []).append(m)

    parrafos = []

    for cat, cat_matches in matches_por_categoria.items():
        # Ordenar por posición de inicio del fragmento y luego por inicio de palabra clave
        matches_ordenados = sorted(cat_matches, key=lambda m: (m['inicio_frag'], m['inicio']))

        grupos = []
        grupo_actual = [matches_ordenados[0]]
        inicio_grupo = matches_ordenados[0]['inicio_frag']
        fin_grupo = matches_ordenados[0]['fin_frag']

        for m in matches_ordenados[1:]:
            if m['inicio_frag'] <= fin_grupo:
                # Hay solapamiento o continuidad dentro de la misma categoría
                fin_grupo = max(fin_grupo, m['fin_frag'])
                grupo_actual.append(m)
            else:
                # Cerrar grupo actual y empezar nuevo grupo
                grupos.append((inicio_grupo, fin_grupo, grupo_actual))
                grupo_actual = [m]
                inicio_grupo = m['inicio_frag']
                fin_grupo = m['fin_frag']

        if grupo_actual:
            grupos.append((inicio_grupo, fin_grupo, grupo_actual))

        for ini, fin, items in grupos:
            frag_texto = texto[ini:fin]
            # Palabras clave únicas preservando el orden de aparición
            pals_unicas = list(dict.fromkeys(m['palabra_clave'] for m in items))

            # Palabras de reducción únicas si existen
            red_unicas = list(dict.fromkeys(m['palabra_reducida'] for m in items if m.get('palabra_reducida')))

            pos_inicio = min(m['inicio'] for m in items)
            pos_fin = max(m['fin'] for m in items)

            parrafos.append({
                'inicio_fragmento': ini,
                'fin_fragmento': fin,
                'fragmento': frag_texto,
                'palabra_clave': separador.join(pals_unicas),
                'categoria': cat,
                'posicion_inicio': pos_inicio,
                'posicion_fin': pos_fin,
                'categorias_set': {cat},
                'palabra_reduccion': separador.join(red_unicas) if red_unicas else ""
            })

    # Ordenar globalmente todos los párrafos de las distintas categorías por su posición en el texto
    parrafos.sort(key=lambda p: (p['inicio_fragmento'], p['posicion_inicio']))
    return parrafos


def extraer_contexto_embargado(texto_completo, palabras_clave_contexto, chars_antes, chars_despues, separador_parrafos="\n\n", separador_keywords=" | ", max_distancia_corte=0, simbolos_corte="", delimitadores_extension=None, max_distancia_extension=0):
    """
    Busca palabras clave de contexto en el texto completo y extrae las ventanas
    de contexto para todas las coincidencias.
    - Si dos o más ventanas se superponen o son adyacentes por spans, se fusionan
    en un único intervalo continuo.
    - Si no comparten span, se concatenan como párrafos separados usando `separador_parrafos`.
    Retorna una tupla: (cadena_contexto, palabras_clave_contexto_str).
    Si no hay coincidencias o no hay palabras clave, retorna ("", "").
    """
    if not texto_completo or not palabras_clave_contexto:
        return "", ""
    coincidencias = buscar_palabras_clave(texto_completo, palabras_clave_contexto)
    if not coincidencias:
        return "", ""

    # Palabras clave únicas encontradas en el contexto, preservando el orden de aparición
    pals_unicas = list(dict.fromkeys(m['palabra_clave'] for m in coincidencias))
    palabras_clave_contexto_str = separador_keywords.join(pals_unicas)

    # Calcular las ventanas de contexto para cada coincidencia encontrada
    ventanas = []
    for m in coincidencias:
        _, inicio_frag, fin_frag = extraer_fragmento(
            texto_completo,
            m['inicio'],
            m['fin'],
            chars_antes,
            chars_despues,
            max_distancia_corte=max_distancia_corte,
            simbolos_corte=simbolos_corte,
            delimitadores_extension=delimitadores_extension,
            max_distancia_extension=max_distancia_extension
        )
        ventanas.append((inicio_frag, fin_frag))

    # Extraer cada párrafo/fragmento continuo y unirlos con el separador
    parrafos = [texto_completo[ini:fin] for ini, fin in fusionar_intervalos(ventanas)]
    return separador_parrafos.join(parrafos), palabras_clave_contexto_str
