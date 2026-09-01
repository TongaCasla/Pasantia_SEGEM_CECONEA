from flask import Flask, request, jsonify, send_from_directory
import os
import unicodedata
import argparse

# Configurar argumentos de línea de comandos
parser = argparse.ArgumentParser(description="Servidor Flask para Contador y Visualizador de Spans")
parser.add_argument(
    "-c", "--columna",
    default=None,
    help="Nombre de la columna del CSV que contiene el texto (si no se especifica, se buscará automáticamente)"
)
# Usar parse_known_args para evitar conflictos con argumentos internos de Flask/reloader
args, unknown = parser.parse_known_args()

app = Flask(__name__, static_folder="static")
app.config['TEXT_COLUMN'] = args.columna



def remove_accents(text):
    if not text:
        return text
    nfd_form = unicodedata.normalize('NFD', text)
    return "".join(c for c in nfd_form if unicodedata.category(c) != 'Mn')



def search_with_exact_offsets(text, search_query):
    """
    Busca apariciones de search_query en text ignorando mayúsculas/minúsculas y acentos,
    pero mapeando de forma exacta los índices de start y end al texto original.
    """
    if not search_query or not text:
        return []

    # Construir string normalizado y mapa de índices: norm_index -> orig_index
    norm_chars = []
    orig_indices = []

    for idx, char in enumerate(text):
        nfd = unicodedata.normalize('NFD', char)
        for c in nfd:
            if unicodedata.category(c) != 'Mn':
                norm_chars.append(c.lower())
                orig_indices.append(idx)

    # Mapear el final de la cadena
    orig_indices.append(len(text))

    norm_text = "".join(norm_chars)

    # Normalizar la query
    query_norm = "".join(
        c.lower() for c in unicodedata.normalize('NFD', search_query)
        if unicodedata.category(c) != 'Mn'
    )

    if not query_norm:
        return []

    query_len = len(query_norm)
    search_results = []
    start_pos = 0

    while True:
        idx = norm_text.find(query_norm, start_pos)
        if idx == -1:
            break

        norm_end = idx + query_len
        orig_start = orig_indices[idx]
        
        # El end en el texto original es la posición inmediatamente posterior al último carácter normalizado del match
        # Si orig_indices tiene suficientes elementos:
        orig_end = orig_indices[norm_end] if norm_end < len(orig_indices) else len(text)

        search_results.append({
            "start": orig_start,
            "end": orig_end,
            "matched_text": text[orig_start:orig_end]
        })
        start_pos = idx + 1

    return search_results


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/count", methods=["POST"])
def count_characters():
    data = request.get_json() or {}
    raw_text = data.get("text", "")
    unescape_csv = data.get("unescape_csv", False)
    search_query = data.get("search_query", "")

    # 1. Normalizar saltos de línea CRLF (\r\n) a LF (\n), tal como lee Python en GLiNER
    text = raw_text.replace("\r\n", "\n")

    # 2. Si el texto proviene de un campo CSV escapado, desescapar comillas dobles ("" -> ")
    if unescape_csv:
        # Convertir comillas dobles internas escapadas ("" -> ")
        text = text.replace('""', '"')
        
        # Eliminar las comillas dobles envolventes del campo CSV
        stripped = text.strip()
        if stripped.startswith('"') and stripped.endswith('"'):
            text = stripped[1:-1]
        elif text.startswith('"'):
            text = text[1:]
        elif stripped.endswith('"'):
            text = text.rstrip()[:-1]

    total = len(text)
    no_spaces = len(text.replace(" ", ""))
    words = len(text.split()) if text.strip() else 0
    lines = text.count("\n") + 1 if text.strip() else 0

    # 3. Buscar apariciones con offset exacto
    search_results = search_with_exact_offsets(text, search_query.strip())

    return jsonify({
        "total": total,
        "no_spaces": no_spaces,
        "words": words,
        "lines": lines,
        "search_results": search_results
    })


@app.route("/api/parse-csv", methods=["POST"])
def parse_csv():
    import csv
    import io

    data = request.get_json() or {}
    csv_text = data.get("csv_text", "")
    selected_doc_id = data.get("selected_doc_id", None)
    custom_text = data.get("text", None)
    unescape_csv = data.get("unescape_csv", True) # Default to GLiNER unescape

    clean_raw_csv = csv_text.strip().lstrip('\ufeff')

    if not clean_raw_csv:
        return jsonify({
            "documents": [],
            "spans_found": [],
            "spans_unfound": [],
            "errors": [],
            "text_processed": ""
        })

    documents_dict = {}
    documents_order = []
    errors = []

    try:
        # Detectar delimitador (coma, punto y coma, tabulación)
        first_line = clean_raw_csv.splitlines()[0] if clean_raw_csv.splitlines() else ""
        if ";" in first_line and first_line.count(";") > first_line.count(","):
            delimiter = ";"
        elif "\t" in first_line and first_line.count("\t") > first_line.count(","):
            delimiter = "\t"
        else:
            delimiter = ","

        f = io.StringIO(clean_raw_csv)
        reader = csv.reader(f, delimiter=delimiter)
        headers_raw = next(reader, None)
        
        if not headers_raw:
            return jsonify({"documents": [], "spans_found": [], "spans_unfound": [], "errors": ["CSV vacío"], "text_processed": ""})

        headers = [h.strip().lstrip('\ufeff').lower() for h in headers_raw]

        # Definir una función auxiliar para resolver el índice de una columna por nombre (case-insensitive)
        def get_col_index_by_name(col_name, fallback_idx):
            if not col_name:
                return fallback_idx
            name_lower = col_name.strip().lower()
            for i, h in enumerate(headers):
                if h.strip().lower() == name_lower:
                    return i
            for i, h in enumerate(headers):
                if name_lower in h.strip().lower():
                    return i
            return fallback_idx

        # Identificar columnas con máxima flexibilidad
        def find_col_idx(patterns, default_idx):
            for i, h in enumerate(headers):
                for p in patterns:
                    if p in h:
                        return i
            return default_idx if default_idx < len(headers) else None

        column_mappings = data.get("column_mappings", {})

        if column_mappings:
            id_idx = get_col_index_by_name(column_mappings.get("id_col"), 0)
            text_idx = get_col_index_by_name(column_mappings.get("text_col"), 1)
            lbl_idx = get_col_index_by_name(column_mappings.get("lbl_col"), 2)
            val_idx = get_col_index_by_name(column_mappings.get("val_col"), 3)
            start_idx = get_col_index_by_name(column_mappings.get("start_col"), 4)
            end_idx = get_col_index_by_name(column_mappings.get("end_col"), 5)
        else:
            id_idx = find_col_idx(['id', 'doc'], 0)
            
            # Usar la columna parametrizada por CLI si se especificó
            text_column_cli = app.config.get('TEXT_COLUMN')
            text_idx = None
            if text_column_cli:
                text_idx = get_col_index_by_name(text_column_cli, None)

            # Si no se especificó o no se encontró, usar la detección flexible predeterminada
            if text_idx is None:
                text_idx = find_col_idx(['texto_limpio', 'clean_text', 'texto', 'text', 'fragmento', 'contexto', 'context'], 1)

            lbl_idx = find_col_idx(['etiqueta', 'label', 'tag', 'entity', 'palabra_clave', 'keyword'], 2)
            val_idx = find_col_idx(['valor', 'value', 'val', 'palabra_clave', 'keyword'], 3)
            start_idx = find_col_idx(['span_inicio', 'spawn_inicio', 'start', 'inicio', 'posicion_inicio'], 4)
            end_idx = find_col_idx(['span_fin', 'spawn_fin', 'end', 'fin', 'posicion_fin'], 5)

        for row_num, row in enumerate(reader, start=2):
            if not row or (len(row) == 1 and not row[0].strip()):
                continue

            doc_id = row[id_idx].strip() if (id_idx is not None and id_idx < len(row) and row[id_idx].strip()) else "Doc_1"
            texto_limpio = row[text_idx] if (text_idx is not None and text_idx < len(row)) else ""
            etiqueta = row[lbl_idx].strip() if (lbl_idx is not None and lbl_idx < len(row)) else ""
            valor = row[val_idx].strip() if (val_idx is not None and val_idx < len(row)) else ""
            
            raw_start = row[start_idx].strip() if (start_idx is not None and start_idx < len(row)) else ""
            raw_end = row[end_idx].strip() if (end_idx is not None and end_idx < len(row)) else ""

            span_inicio = int(raw_start) if raw_start.isdigit() or (raw_start.startswith('-') and raw_start[1:].isdigit()) else None
            span_fin = int(raw_end) if raw_end.isdigit() or (raw_end.startswith('-') and raw_end[1:].isdigit()) else None

            if doc_id not in documents_dict:
                documents_dict[doc_id] = {
                    "id": doc_id,
                    "fragments": [],  # Lista de dicts: {"text": ..., "spans": []}
                }
                documents_order.append(doc_id)

            # Buscar si ya existe este fragmento en el documento para agrupar
            found_fragment = None
            for frag in documents_dict[doc_id]["fragments"]:
                if frag["text"] == texto_limpio:
                    found_fragment = frag
                    break

            if found_fragment is None:
                found_fragment = {
                    "text": texto_limpio,
                    "spans": []
                }
                documents_dict[doc_id]["fragments"].append(found_fragment)

            found_fragment["spans"].append({
                "line_num": row_num,
                "etiqueta": etiqueta,
                "valor": valor,
                "span_inicio": span_inicio,
                "span_fin": span_fin,
                "row": row
            })

        # Consolidar y concatenar los fragmentos de cada documento
        for doc_id in documents_order:
            doc_data = documents_dict[doc_id]
            concatenated_text = ""
            consolidated_spans = []

            for i, frag in enumerate(doc_data["fragments"]):
                frag_text = frag["text"]
                
                # Agregar separador de dos saltos de línea si no es el primer fragmento
                if i > 0:
                    separator = "\n\n"
                    offset = len(concatenated_text) + len(separator)
                    concatenated_text += separator
                else:
                    offset = 0

                # Ajustar coordenadas agregando el offset acumulado
                for span in frag["spans"]:
                    adj_span = span.copy()
                    if adj_span["span_inicio"] is not None:
                        adj_span["span_inicio"] += offset
                    if adj_span["span_fin"] is not None:
                        adj_span["span_fin"] += offset
                    # Guardamos el offset y longitud de su segmento para búsquedas de fallback
                    adj_span["frag_offset"] = offset
                    adj_span["frag_len"] = len(frag_text)
                    consolidated_spans.append(adj_span)

                concatenated_text += frag_text

            doc_data["texto_limpio"] = concatenated_text
            doc_data["spans"] = consolidated_spans

    except Exception as e:
        return jsonify({"documents": [], "spans_found": [], "spans_unfound": [], "errors": [f"Error procesando CSV: {str(e)}"], "text_processed": ""})

    doc_list = []
    for idx, doc_id in enumerate(documents_order, start=1):
        doc_list.append({
            "id": doc_id,
            "label": f"{idx}. {doc_id}",
            "texto_limpio": documents_dict[doc_id]["texto_limpio"]
        })

    if not doc_list:
        return jsonify({"documents": [], "spans_found": [], "spans_unfound": [], "errors": ["No se encontraron filas con datos en el CSV"], "text_processed": ""})

    active_doc_id = selected_doc_id if selected_doc_id in documents_dict else documents_order[0]
    target_doc = documents_dict[active_doc_id]

    raw_text = custom_text if custom_text is not None else target_doc["texto_limpio"]

    text_processed = raw_text.replace("\r\n", "\n")
    if unescape_csv:
        text_processed = text_processed.replace('""', '"')
        stripped = text_processed.strip()
        if stripped.startswith('"') and stripped.endswith('"'):
            text_processed = stripped[1:-1]
        elif text_processed.startswith('"'):
            text_processed = text_processed[1:]
        elif stripped.endswith('"'):
            text_processed = text_processed.rstrip()[:-1]

    spans_found = []
    spans_unfound = []

    for s in target_doc["spans"]:
        inicio = s["span_inicio"]
        fin = s["span_fin"]
        valor = s["valor"]
        etiqueta = s["etiqueta"]

        # Función auxiliar para normalizar cadenas para comparación insensible a acentos/mayúsculas
        def normalize_for_comparison(t):
            if not t:
                return ""
            return remove_accents(t).lower().strip()

        # Verificar si las coordenadas son válidas
        valid_range = (inicio is not None and fin is not None and inicio >= 0 and fin > inicio and fin <= len(text_processed))
        real_text = text_processed[inicio:fin] if valid_range else ""
        match_exact = (normalize_for_comparison(real_text) == normalize_for_comparison(valor)) if valid_range else False

        # 1. Fallback: Restar un posible offset si la fila tiene alguna columna de offset/inicio_fragmento
        if not match_exact and valor and text_processed and (inicio is not None and fin is not None):
            row_data = s.get("row", [])
            for col_idx, col_name in enumerate(headers):
                if 'inicio_fragmento' in col_name or 'offset' in col_name or 'start_fragment' in col_name:
                    if col_idx < len(row_data):
                        offset_str = row_data[col_idx].strip()
                        if offset_str.isdigit():
                            offset_val = int(offset_str)
                            adj_inicio = inicio - offset_val
                            adj_fin = fin - offset_val
                            adj_valid = (adj_inicio >= 0 and adj_fin > adj_inicio and adj_fin <= len(text_processed))
                            adj_real = text_processed[adj_inicio:adj_fin] if adj_valid else ""
                            if normalize_for_comparison(adj_real) == normalize_for_comparison(valor):
                                inicio = adj_inicio
                                fin = adj_fin
                                real_text = adj_real
                                match_exact = True
                                valid_range = True
                                break

        # 2. Fallback: Búsqueda del valor dentro del segmento del fragmento sin importar acentos ni mayúsculas
        if not match_exact and valor and text_processed:
            frag_offset = s.get("frag_offset", 0)
            frag_len = s.get("frag_len", len(text_processed))
            frag_text_segment = text_processed[frag_offset : frag_offset + frag_len]
            
            matches = search_with_exact_offsets(frag_text_segment, valor)
            if matches:
                best_match = matches[0]
                inicio = frag_offset + best_match["start"]
                fin = frag_offset + best_match["end"]
                real_text = text_processed[inicio:fin]
                match_exact = True
                valid_range = True

        # 3. Fallback: Mismatch de 15 caracteres (como comillas extras) sin importar acentos ni mayúsculas
        if not match_exact and valor and text_processed:
            search_min = max(0, (inicio if inicio is not None else 0) - 15)
            search_max = min(len(text_processed), (fin if fin is not None else 0) + 15)
            sub_text = text_processed[search_min:search_max]
            matches = search_with_exact_offsets(sub_text, valor)
            if matches:
                best_match = matches[0]
                inicio = search_min + best_match["start"]
                fin = search_min + best_match["end"]
                real_text = text_processed[inicio:fin]
                match_exact = True
                valid_range = True

        if valid_range and (match_exact or real_text.strip()):
            spans_found.append({
                "line_num": s["line_num"],
                "etiqueta": etiqueta,
                "valor": valor,
                "span_inicio": inicio,
                "span_fin": fin,
                "real_text": real_text,
                "match_exact": match_exact
            })
        else:
            spans_unfound.append({
                "line_num": s["line_num"],
                "etiqueta": etiqueta,
                "valor": valor,
                "span_inicio": inicio,
                "span_fin": fin,
                "real_text": real_text,
                "motivo": "El rango no coincide con el valor ni contiene texto"
            })

    search_query = data.get("search_query", "").strip()
    search_results = search_with_exact_offsets(text_processed, search_query) if search_query else []

    def get_col_name(idx):
        if idx is not None and idx < len(headers_raw):
            return headers_raw[idx]
        return ""

    mappings_used = {
        "id_col": get_col_name(id_idx),
        "text_col": get_col_name(text_idx),
        "lbl_col": get_col_name(lbl_idx),
        "val_col": get_col_name(val_idx),
        "start_col": get_col_name(start_idx),
        "end_col": get_col_name(end_idx),
    }

    return jsonify({
        "selected_doc_id": active_doc_id,
        "documents": doc_list,
        "spans_found": spans_found,
        "spans_unfound": spans_unfound,
        "search_results": search_results,
        "errors": errors,
        "text_processed": text_processed,
        "headers": headers_raw,
        "mappings": mappings_used
    })


if __name__ == "__main__":
    if app.config.get('TEXT_COLUMN'):
        print(f"[*] Configurado por CLI el campo de texto CSV: '{app.config['TEXT_COLUMN']}'")
    else:
        print("[*] Usando detección automática para el campo de texto CSV (texto_limpio, clean_text, etc.)")
    app.run(debug=True, port=5000)
