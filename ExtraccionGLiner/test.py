from pathlib import Path

text = Path("ej.txt").read_text(encoding="utf-8")
needle = "LEVY, VERONICA LILIANA"

idx = text.find(needle)

print("longitud del texto:", len(text))
print("indice encontrado:", idx)
print("substring:", repr(text[idx:idx + len(needle)]))
print("contexto:", repr(text[max(0, idx - 20):idx + len(needle) + 20]))

if idx == -1:
    print("No se encontró la entidad en el texto.")
else:
    print("caracteres previos:", idx)
    print("caracteres posteriores:", len(text) - idx - len(needle))

