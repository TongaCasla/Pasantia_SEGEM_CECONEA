from flask import Flask, request, jsonify, send_from_directory
import os

app = Flask(__name__, static_folder="static")


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

    # 3. Buscar TODAS las apariciones de forma insensible a mayúsculas/minúsculas
    search_results = []
    query_str = search_query.strip()
    if query_str:
        text_lower = text.lower()
        query_lower = query_str.lower()
        query_len = len(query_str)
        
        start_pos = 0
        while True:
            idx = text_lower.find(query_lower, start_pos)
            if idx == -1:
                break
            end_idx = idx + query_len
            search_results.append({
                "start": idx,
                "end": end_idx,
                "matched_text": text[idx:end_idx]
            })
            start_pos = idx + 1

    return jsonify({
        "total": total,
        "no_spaces": no_spaces,
        "words": words,
        "lines": lines,
        "search_results": search_results
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
