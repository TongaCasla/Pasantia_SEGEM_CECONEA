"""
normalizacion.py - Funciones de normalización y comparación para entidades judiciales.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional, Union


def normalizar_dni(dni: Union[str, int, float, None]) -> str:
    """
    Normaliza un DNI eliminando puntos, guiones, espacios y ceros a la izquierda no significativos.
    Retorna solo los dígitos o cadena vacía si no es válido.
    """
    if dni is None:
        return ""
    texto = str(dni).strip()
    if not texto or texto.lower() in ("nan", "none", "null", "s/d", "no indica"):
        return ""
    
    # Si viene con decimales de float (ej: "12345678.0")
    if re.match(r"^\d+\.0$", texto):
        texto = texto[:-2]
        
    solo_digitos = re.sub(r"\D", "", texto)
    return solo_digitos.lstrip("0") if solo_digitos else ""


def normalizar_cuit(cuit: Union[str, int, float, None]) -> str:
    """
    Normaliza un CUIT/CUIL eliminando puntos, guiones y espacios.
    Retorna solo los dígitos o cadena vacía.
    """
    if cuit is None:
        return ""
    texto = str(cuit).strip()
    if not texto or texto.lower() in ("nan", "none", "null", "s/d", "no indica"):
        return ""
    
    # Si viene con decimales de float
    if re.match(r"^\d+\.0$", texto):
        texto = texto[:-2]
        
    solo_digitos = re.sub(r"\D", "", texto)
    return solo_digitos


def normalizar_monto(monto: Union[str, int, float, None]) -> Optional[float]:
    """
    Parsea un monto monetario en formato argentino ($ 1.234.567,89) o estándar (1234567.89).
    Retorna un float o None si no se puede parsear.
    """
    if monto is None:
        return None
    if isinstance(monto, (int, float)):
        return float(monto)
    
    texto = str(monto).strip()
    if not texto or texto.lower() in ("nan", "none", "null", "s/d", "no indica", "no especifica"):
        return None
    
    # Quitar símbolos de moneda, letras y espacios
    texto = re.sub(r"[^\d.,]", "", texto)
    if not texto:
        return None
    
    # Manejar formatos comunes:
    # Caso 1: Ambos '.' y ',' presentes -> ej: 1.234.567,89 o 1,234,567.89
    if "." in texto and "," in texto:
        ultimo_punto = texto.rfind(".")
        ultima_coma = texto.rfind(",")
        if ultima_coma > ultimo_punto:
            # Formato latino/argentino: 1.234.567,89 -> miles con '.', decimal con ','
            texto = texto.replace(".", "").replace(",", ".")
        else:
            # Formato anglosajón: 1,234,567.89 -> miles con ',', decimal con '.'
            texto = texto.replace(",", "")
    elif "," in texto:
        # Solo coma: si tiene 1 o 2 decimales después de la coma -> es separador decimal
        partes = texto.split(",")
        if len(partes) == 2 and len(partes[1]) <= 2:
            texto = partes[0] + "." + partes[1]
        else:
            # Podría ser separador de miles si no tiene decimales claros o tiene múltiples comas
            texto = texto.replace(",", "")
    elif "." in texto:
        # Solo punto: si tiene 3 dígitos al final y partes anteriores -> podría ser separador de miles
        partes = texto.split(".")
        if len(partes) > 1 and all(len(p) == 3 for p in partes[1:]):
            texto = "".join(partes)
        elif len(partes) == 2 and len(partes[1]) == 3 and len(partes[0]) <= 3:
            # Ambiguo: ej "100.000" suele ser cien mil en Argentina
            texto = "".join(partes)
        else:
            # Asumir punto decimal estándar
            pass

    try:
        return float(texto)
    except (ValueError, TypeError):
        return None


def normalizar_nombre(nombre: Union[str, None]) -> str:
    """
    Normaliza un nombre: minúsculas, sin acentos/diacríticos, sin signos de puntuación,
    espacios colapsados.
    """
    if not nombre:
        return ""
    texto = str(nombre).strip()
    if texto.lower() in ("nan", "none", "null", "s/d", "no indica"):
        return ""
    
    # Eliminar diacríticos (acentos)
    nfkd = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    
    # Convertir a minúsculas y reemplazar puntuación por espacios
    limpio = re.sub(r"[^\w\s]", " ", sin_tildes.lower())
    # Colapsar espacios múltiples
    return re.sub(r"\s+", " ", limpio).strip()


def similitud_nombre(nombre1: str, nombre2: str) -> float:
    """
    Calcula la similitud normalizada entre dos nombres [0.0, 1.0].
    Permite orden permutado de palabras (ej: 'JUAN PEREZ' vs 'PEREZ JUAN').
    """
    n1 = normalizar_nombre(nombre1)
    n2 = normalizar_nombre(nombre2)
    if not n1 and not n2:
        return 1.0
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0

    # Similitud directa
    sim_directa = SequenceMatcher(None, n1, n2).ratio()

    # Similitud ordenando tokens
    tokens1 = " ".join(sorted(n1.split()))
    tokens2 = " ".join(sorted(n2.split()))
    sim_tokens = SequenceMatcher(None, tokens1, tokens2).ratio()

    return max(sim_directa, sim_tokens)


def fuzzy_match_nombre(nombre1: str, nombre2: str, umbral: float = 0.85) -> bool:
    """
    Compara dos nombres con fuzzy matching y determina si coinciden según un umbral.
    """
    return similitud_nombre(nombre1, nombre2) >= umbral


def normalizar_cuenta(cuenta: Union[str, int, float, None]) -> str:
    """
    Normaliza un número de cuenta judicial eliminando barras, guiones, espacios y ceros a la izquierda.
    """
    if cuenta is None:
        return ""
    texto = str(cuenta).strip()
    if not texto or texto.lower() in ("nan", "none", "null", "s/d", "no indica", "no especifica"):
        return ""
    
    # Quitar decimales si vino como float
    if re.match(r"^\d+\.0$", texto):
        texto = texto[:-2]
        
    # Mantener solo dígitos y letras mayúsculas (por si hay identificadores alfanuméricos)
    limpio = re.sub(r"[\s\-\./_]", "", texto.upper())
    return limpio
