"""
extraccion_fragmento: keyword-driven text fragment extraction.

Usage:
    from extraccion_fragmento import ExtraccionFragmento, ExtractorConfig

    extractor = ExtraccionFragmento.from_files("palabras_clave.txt", config=ExtractorConfig())
    resultado = extractor.extraer(texto)
"""
from .extractor import ExtraccionFragmento
from .models import ExtractorConfig, Fragmento, ResultadoExtraccion

__all__ = ["ExtraccionFragmento", "ExtractorConfig", "Fragmento", "ResultadoExtraccion"]
__version__ = "1.0.0"
