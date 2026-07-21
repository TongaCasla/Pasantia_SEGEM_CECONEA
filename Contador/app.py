from flask import Flask, request, jsonify, send_from_directory
import os

app = Flask(__name__, static_folder="static")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/count", methods=["POST"])
def count_characters():
    data = request.get_json()
    text = data.get("text", "")

    total = len(text)
    no_spaces = len(text.replace(" ", ""))
    words = len(text.split()) if text.strip() else 0
    lines = text.count("\n") + 1 if text.strip() else 0

    return jsonify({
        "total": total,
        "no_spaces": no_spaces,
        "words": words,
        "lines": lines,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
