"""
Configuration and result models for ExtraccionFragmento.
"""
import logging
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

from .normalizer import normalizar_nombre_categoria
from .window import parsear_delimitadores_extension, parsear_simbolos_corte

logger = logging.getLogger(__name__)


def parsear_chars_categoria(cadena_config):
    """
    Parsea la cadena de configuración de caracteres por categoría.
    Formato: "Categoria1:antes:despues,Categoria2:antes:despues"
    Retorna un diccionario {categoria_normalizada: (antes, despues)}.
    """
    if not cadena_config:
        return {}
    resultado = {}
    entradas = cadena_config.split(',')
    for entrada in entradas:
        partes = entrada.strip().split(':')
        if len(partes) == 3:
            cat_nombre = normalizar_nombre_categoria(partes[0])
            try:
                antes = int(partes[1].strip())
                despues = int(partes[2].strip())
                resultado[cat_nombre] = (antes, despues)
            except ValueError:
                logger.warning("Valores de caracteres inválidos en '%s'. Ignorando.", entrada.strip())
        elif entrada.strip():
            logger.warning(
                "Formato inválido en entrada de caracteres por categoría '%s'. "
                "Formato esperado: 'Categoria:antes:despues'.", entrada.strip()
            )
    return resultado


def obtener_chars_para_categoria(categoria, dict_chars, global_antes, global_despues):
    """
    Obtiene los valores (antes, despues) para una categoría dada.
    Si la categoría está configurada con 0:0, retorna None (indica que no debe extraerse).
    Si no está configurada, retorna (global_antes, global_despues).
    """
    if not dict_chars or not categoria:
        return (global_antes, global_despues)

    cat_norm = normalizar_nombre_categoria(categoria)

    # Búsqueda directa
    if cat_norm in dict_chars:
        antes, despues = dict_chars[cat_norm]
        if antes == 0 and despues == 0:
            return None
        return (antes, despues)

    # Búsqueda por prefijo / compatibilidad
    for k, v in dict_chars.items():
        if cat_norm.startswith(k) or k.startswith(cat_norm):
            if v[0] == 0 and v[1] == 0:
                return None
            return v

    return (global_antes, global_despues)


def _normalizar_chars_categoria(valor):
    if not valor:
        return {}
    if isinstance(valor, str):
        return parsear_chars_categoria(valor)
    return {normalizar_nombre_categoria(k): (int(v[0]), int(v[1])) for k, v in dict(valor).items()}


@dataclass
class ExtractorConfig:
    """
    Behavior of the extractor. String values for ``chars_por_categoria``,
    ``delimitadores_extension`` and ``simbolos_corte`` are accepted (CLI
    format) and normalized to dict/lists on creation.
    """
    chars_antes: int = 200
    chars_despues: int = 200
    habilitar_reduccion: bool = True
    habilitar_agrupacion: bool = True
    separador: str = " | "
    chars_por_categoria: Optional[Union[str, Dict[str, Sequence[int]]]] = None
    delimitadores_extension: Optional[Union[str, Sequence[str]]] = None
    max_distancia_extension: int = 0
    simbolos_corte: Optional[Union[str, Sequence[str]]] = None
    max_distancia_corte: int = 0
    chars_antes_contexto: int = 200
    chars_despues_contexto: int = 200
    separador_contexto: str = "\n\n"
    categoria_reduccion: str = "datos_embargado"
    claves_requieren_numero: Tuple[str, ...] = ("dni", "cuil", "cuit", "doc")

    def __post_init__(self):
        for nombre in ("chars_antes", "chars_despues", "max_distancia_extension",
                       "max_distancia_corte", "chars_antes_contexto", "chars_despues_contexto"):
            valor = getattr(self, nombre)
            if not isinstance(valor, int) or valor < 0:
                raise ValueError(f"'{nombre}' debe ser un entero >= 0 (recibido: {valor!r}).")
        self.chars_por_categoria = _normalizar_chars_categoria(self.chars_por_categoria)
        self.delimitadores_extension = parsear_delimitadores_extension(self.delimitadores_extension)
        self.simbolos_corte = parsear_simbolos_corte(self.simbolos_corte)
        self.categoria_reduccion = normalizar_nombre_categoria(self.categoria_reduccion or "")
        self.claves_requieren_numero = tuple(k.strip().lower() for k in (self.claves_requieren_numero or ()) if k.strip())


@dataclass(frozen=True)
class Fragmento:
    """A single extracted fragment (or merged paragraph when grouping is on)."""
    palabra_clave: str
    categoria: str
    fragmento: str
    posicion_inicio: int
    posicion_fin: int
    inicio_fragmento: int
    fin_fragmento: int
    palabra_reduccion: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class ResultadoExtraccion:
    """Result of processing one document."""
    fragmentos_principales: List[Fragmento] = field(default_factory=list)
    fragmentos_reducidos: List[Fragmento] = field(default_factory=list)
    contexto_embargado: str = ""
    palabras_clave_contexto: str = ""
    categorias_encontradas: Set[str] = field(default_factory=set)
    categorias_faltantes: List[str] = field(default_factory=list)

    @property
    def tiene_coincidencias(self):
        return bool(self.fragmentos_principales)

    def to_dict(self):
        data = asdict(self)
        data["categorias_encontradas"] = sorted(self.categorias_encontradas)
        return data
