"""
Fragment window computation: initial window, outward extension to semantic
delimiters and inward cut / word-boundary adjustment.
"""
import re


def parsear_simbolos_corte(cadena):
    """
    Parsea la cadena de símbolos o secuencias de corte.
    Soporta:
      - Símbolos individuales clásicos: ',', ',;.'
      - Secuencias compuestas: '".\\n"', '.\\n', '". ", ,'
      - Decodificación de escapes: \\n -> salto de línea, \\t, etc.
    Retorna una lista de strings con los símbolos/secuencias a buscar.
    """
    if not cadena:
        return []
    if isinstance(cadena, (list, tuple)):
        items = list(cadena)
    else:
        cadena_limpia = str(cadena).replace('/n', '\\n')
        has_newline = '\n' in cadena_limpia or '\\n' in cadena_limpia
        if '"' in cadena_limpia or "'" in cadena_limpia:
            patron = r'''(?:["][^"]*["]|['][^']*[']|[^,"'|]+)'''
            tokens = re.findall(patron, cadena_limpia)
            items = []
            for t in tokens:
                if not t.strip(' \t\r\n'):
                    continue
                ts = t.strip(' \t\r\n')
                if (ts.startswith('"') and ts.endswith('"')) or (ts.startswith("'") and ts.endswith("'")):
                    items.append(ts[1:-1])
                else:
                    items.append(t.lstrip(' \t'))
        elif has_newline:
            cadena_norm = cadena_limpia.replace('\\n', '\n')
            if ',' in cadena_norm or '|' in cadena_norm:
                items = [t.strip(' \t\r') for t in re.split(r'[,|]', cadena_norm) if t.strip(' \t\r')]
            else:
                items = [cadena_norm.strip(' \t\r')]
        elif ',' in cadena_limpia and ' ' in cadena_limpia:
            items = [t.strip() for t in cadena_limpia.split(',') if t.strip()]
        else:
            items = list(cadena_limpia.strip())

    simbolos = []
    for item in items:
        val = item.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t')
        if val and val not in simbolos:
            simbolos.append(val)

    return simbolos


def parsear_delimitadores_extension(cadena):
    """
    Parsea la cadena de delimitadores para extensión de fragmentos.
    Soporta formatos como:
      - '". ", \\n'
      - '". " | "\\n"'
      - '. , \\n'
      - '/n' (se interpreta como salto de línea '\\n')
    Retorna una lista de strings con los delimitadores no vacíos.
    """
    if not cadena:
        return []
    if isinstance(cadena, (list, tuple)):
        items = list(cadena)
    else:
        cadena_limpia = str(cadena).replace('/n', '\\n')
        patron = r'''(?:["][^"]*["]|['][^']*[']|[^,"'|]+)'''
        tokens = re.findall(patron, cadena_limpia)
        items = []
        for t in tokens:
            if not t.strip():
                continue
            t_strip = t.strip()
            if (t_strip.startswith('"') and t_strip.endswith('"')) or (t_strip.startswith("'") and t_strip.endswith("'")):
                items.append(t_strip[1:-1])
            else:
                # Quitar solo espacios previos al delimitador, preservando si termina en espacio (ej: '. ')
                items.append(t.lstrip(' \t'))

    delimitadores = []
    for item in items:
        val = item.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t')
        if val and val not in delimitadores:
            delimitadores.append(val)

    return delimitadores


def ajustar_limites_palabra(texto, inicio_frag, fin_frag, ajustar_inicio=True, ajustar_fin=True, max_distancia_corte=0, simbolos_corte=""):
    """
    Ajusta los límites inicio_frag y fin_frag.
    Si se proporciona max_distancia_corte > 0 y simbolos_corte, busca hacia ADENTRO
    del fragmento hasta max_distancia_corte caracteres. Si encuentra algún símbolo
    o secuencia (ej. ',', '.\\n', ';'), recorta el fragmento ahí.
    Si no lo encuentra, usa el comportamiento original (expandir hasta espacio).
    """
    n = len(texto)
    encontro_corte_inicio = False
    encontro_corte_fin = False

    simbolos = parsear_simbolos_corte(simbolos_corte) if isinstance(simbolos_corte, str) else list(simbolos_corte or [])

    if max_distancia_corte > 0 and simbolos:
        if ajustar_inicio:
            limite_busqueda = min(inicio_frag + max_distancia_corte, fin_frag)
            for i in range(inicio_frag, limite_busqueda):
                coincidio = False
                for s in simbolos:
                    len_s = len(s)
                    if i + len_s <= fin_frag and texto[i : i + len_s] == s:
                        inicio_frag = i + len_s
                        while inicio_frag < fin_frag and texto[inicio_frag] in (' ', '\t'):
                            inicio_frag += 1
                        encontro_corte_inicio = True
                        coincidio = True
                        break
                if coincidio:
                    break

        if ajustar_fin:
            limite_busqueda = max(fin_frag - max_distancia_corte, inicio_frag)
            for i in range(fin_frag - 1, limite_busqueda - 1, -1):
                coincidio = False
                for s in simbolos:
                    len_s = len(s)
                    if i + len_s <= fin_frag and texto[i : i + len_s] == s:
                        len_punc = len(s.rstrip(' \t\r\n'))
                        fin_frag = i + len_punc if len_punc > 0 else i
                        encontro_corte_fin = True
                        coincidio = True
                        break
                if coincidio:
                    break

    if ajustar_inicio and not encontro_corte_inicio:
        while inicio_frag > 0 and not texto[inicio_frag - 1].isspace() and not texto[inicio_frag].isspace():
            inicio_frag -= 1

    if ajustar_fin and not encontro_corte_fin:
        while fin_frag < n and not texto[fin_frag - 1].isspace() and not texto[fin_frag].isspace():
            fin_frag += 1

    return inicio_frag, fin_frag


def extender_limites_fragmento(
    texto,
    inicio_frag,
    fin_frag,
    delimitadores,
    max_distancia=0,
    extender_inicio=True,
    extender_fin=True
):
    """
    Extiende los límites del fragmento (inicio_frag y fin_frag) hacia afuera
    hasta encontrar alguno de los delimitadores especificados (ej: '. ', '\\n').

    Parámetros:
      - texto: Texto completo del documento.
      - inicio_frag: Posición actual de inicio del fragmento.
      - fin_frag: Posición actual de fin del fragmento.
      - delimitadores: Lista de cadenas delimitadoras (ej: ['. ', '\\n']).
      - max_distancia: Cantidad máxima de caracteres hacia afuera a explorar.
                       0 significa sin límite de distancia (hasta el borde del texto).
      - extender_inicio: Si True, intenta extender hacia la izquierda (hacia atrás).
      - extender_fin: Si True, intenta extender hacia la derecha (hacia adelante).

    Retorna:
      - (nuevo_inicio, nuevo_fin)
    """
    if not texto or not delimitadores or (not extender_inicio and not extender_fin):
        return inicio_frag, fin_frag

    n = len(texto)
    inicio_frag = max(0, min(inicio_frag, n))
    fin_frag = max(inicio_frag, min(fin_frag, n))

    # --- Extensión hacia atrás (inicio) ---
    if extender_inicio and inicio_frag > 0:
        # Verificar si ya empieza en un límite natural / delimitador
        ya_empieza = False
        txt_prev = texto[:inicio_frag]
        for delim in delimitadores:
            if txt_prev.endswith(delim) or txt_prev.rstrip(' \t').endswith(delim.rstrip(' \t')):
                ya_empieza = True
                break

        if not ya_empieza:
            limite_min = max(0, inicio_frag - max_distancia) if max_distancia > 0 else 0
            sub = texto[limite_min:inicio_frag]
            mejor_pos_fin = -1

            for delim in delimitadores:
                if not delim:
                    continue
                pos = sub.rfind(delim)
                if pos != -1:
                    pos_fin = limite_min + pos + len(delim)
                    if pos_fin > mejor_pos_fin:
                        mejor_pos_fin = pos_fin

            if mejor_pos_fin != -1:
                nuevo_inicio = mejor_pos_fin
                while nuevo_inicio < fin_frag and texto[nuevo_inicio] in (' ', '\t'):
                    nuevo_inicio += 1
                inicio_frag = nuevo_inicio

    # --- Extensión hacia adelante (fin) ---
    if extender_fin and fin_frag < n:
        # Verificar si ya termina en un límite natural / delimitador
        ya_termina = False
        txt_hasta_fin = texto[:fin_frag]
        for delim in delimitadores:
            punc = delim.rstrip(' \t\r\n')
            if punc:
                if txt_hasta_fin.endswith(punc) and (fin_frag >= n or texto[fin_frag].isspace()):
                    ya_termina = True
                    break
            else:
                if txt_hasta_fin.endswith(delim) or (fin_frag < n and texto[fin_frag:fin_frag+len(delim)] == delim):
                    ya_termina = True
                    break

        if not ya_termina:
            limite_max = min(n, fin_frag + max_distancia) if max_distancia > 0 else n
            sub = texto[fin_frag:limite_max]
            mejor_pos_corte = -1

            for delim in delimitadores:
                if not delim:
                    continue
                pos = sub.find(delim)
                if pos != -1:
                    idx_en_texto = fin_frag + pos
                    len_punc = len(delim.rstrip(' \t\r\n'))
                    pos_corte = idx_en_texto + len_punc
                    if mejor_pos_corte == -1 or pos_corte < mejor_pos_corte:
                        mejor_pos_corte = pos_corte

            if mejor_pos_corte != -1:
                fin_frag = mejor_pos_corte

    return inicio_frag, fin_frag


def extraer_fragmento(texto, inicio, fin, chars_antes, chars_despues, max_distancia_corte=0, simbolos_corte="", delimitadores_extension=None, max_distancia_extension=0):
    """
    Extrae la ventana de contexto alrededor de la coincidencia.
    Ajusta los límites según extensión hacia delimitadores, corte y/o por palabra.
    Retorna el fragmento y las posiciones de inicio/fin correspondientes.
    """
    inicio_frag = max(0, inicio - chars_antes)
    fin_frag = min(len(texto), fin + chars_despues)

    if delimitadores_extension:
        inicio_frag, fin_frag = extender_limites_fragmento(
            texto,
            inicio_frag,
            fin_frag,
            delimitadores_extension,
            max_distancia=max_distancia_extension,
            extender_inicio=(chars_antes > 0),
            extender_fin=(chars_despues > 0)
        )

    inicio_frag, fin_frag = ajustar_limites_palabra(
        texto,
        inicio_frag,
        fin_frag,
        ajustar_inicio=(chars_antes > 0),
        ajustar_fin=(chars_despues > 0),
        max_distancia_corte=max_distancia_corte,
        simbolos_corte=simbolos_corte
    )

    fragmento = texto[inicio_frag:fin_frag]
    return fragmento, inicio_frag, fin_frag
