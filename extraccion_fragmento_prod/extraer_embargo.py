"""
Legacy entry point kept for backward compatibility.

The implementation lives in the ``extraccion_fragmento`` package:
    python extraer_embargo.py input.csv [opciones]
is equivalent to:
    python -m extraccion_fragmento input.csv [opciones]
"""
from extraccion_fragmento.cli import main

if __name__ == "__main__":
    main()
