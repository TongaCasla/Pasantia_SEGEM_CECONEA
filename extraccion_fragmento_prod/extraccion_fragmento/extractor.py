"""
ExtraccionFragmento: in-memory black-box facade.

Receives a document as a string and returns a ``ResultadoExtraccion``.
It never reads CSVs, never writes files and never calls ``sys.exit``.
"""
from typing import Iterable, Iterator, Mapping, Optional

from .loaders import cargar_palabras_clave, cargar_palabras_reduccion
from .merger import agrupar_fragmentos_superpuestos, extraer_contexto_embargado
from .models import ExtractorConfig, Fragmento, ResultadoExtraccion, obtener_chars_para_categoria
from .normalizer import buscar_palabras_clave
from .reduction import evaluar_reduccion, preparar_patrones_reduccion
from .window import extraer_fragmento

CATEGORIA_POR_DEFECTO = 'sin_categoria'


def _normalizar_entradas_keywords(palabras):
    """
    Accepts keywords as:
      - ``{"Categoria": ["palabra1", "palabra2"]}``
      - ``[{"palabra": "...", "categoria": "..."}]``
      - ``[("palabra", "categoria")]``
      - ``["palabra"]`` (category ``sin_categoria``)
    Returns ``[{'palabra': str, 'categoria': str}]``.
    """
    if not palabras:
        return []
    if isinstance(palabras, Mapping):
        return [
            {'palabra': p, 'categoria': cat}
            for cat, lista in palabras.items()
            for p in lista
            if p and p.strip()
        ]
    entradas = []
    for item in palabras:
        if isinstance(item, Mapping):
            palabra, categoria = item.get('palabra'), item.get('categoria') or CATEGORIA_POR_DEFECTO
        elif isinstance(item, (tuple, list)):
            palabra, categoria = item[0], (item[1] if len(item) > 1 else CATEGORIA_POR_DEFECTO)
        else:
            palabra, categoria = item, CATEGORIA_POR_DEFECTO
        if palabra and str(palabra).strip():
            entradas.append({'palabra': str(palabra), 'categoria': categoria})
    return entradas


def _parrafo_a_fragmento(p):
    return Fragmento(
        palabra_clave=p['palabra_clave'],
        categoria=p['categoria'],
        fragmento=p['fragmento'],
        posicion_inicio=p['posicion_inicio'],
        posicion_fin=p['posicion_fin'],
        inicio_fragmento=p['inicio_fragmento'],
        fin_fragmento=p['fin_fragmento'],
        palabra_reduccion=p['palabra_reduccion'] or "",
    )


def _item_a_fragmento(item):
    return Fragmento(
        palabra_clave=item['palabra_clave'],
        categoria=item['categoria'],
        fragmento=item['fragmento'],
        posicion_inicio=item['inicio'],
        posicion_fin=item['fin'],
        inicio_fragmento=item['inicio_frag'],
        fin_fragmento=item['fin_frag'],
        palabra_reduccion=item['palabra_reducida'] or "",
    )


class ExtraccionFragmento:
    """
    Keyword-driven fragment extractor.

    Instantiate once and reuse it for every document: keyword lists and
    reduction patterns are prepared on construction.
    """

    def __init__(self, palabras_clave, config: Optional[ExtractorConfig] = None,
                 palabras_reduccion=None, palabras_clave_contexto=None):
        self.config = config or ExtractorConfig()
        self._palabras_clave = _normalizar_entradas_keywords(palabras_clave)
        if not self._palabras_clave:
            raise ValueError("Se requiere al menos una palabra clave.")
        self._palabras_contexto = _normalizar_entradas_keywords(palabras_clave_contexto)
        self._palabras_reduccion = [p.strip() for p in (palabras_reduccion or []) if p and p.strip()]
        self._patrones_reduccion = preparar_patrones_reduccion(self._palabras_reduccion)
        self._categorias = list(dict.fromkeys(e['categoria'] for e in self._palabras_clave))

    @classmethod
    def from_files(cls, keywords_path, reduction_path=None, context_keywords_path=None,
                   config: Optional[ExtractorConfig] = None):
        """Builds the extractor from the plain-text configuration files."""
        palabras = cargar_palabras_clave(keywords_path)
        reduccion = cargar_palabras_reduccion(reduction_path) if reduction_path else None
        contexto = cargar_palabras_clave(context_keywords_path) if context_keywords_path else None
        return cls(palabras, config=config, palabras_reduccion=reduccion, palabras_clave_contexto=contexto)

    @property
    def categorias(self):
        """Categories defined by the keywords, in order of appearance."""
        return list(self._categorias)

    @property
    def palabras_clave(self):
        return [dict(e) for e in self._palabras_clave]

    @property
    def palabras_reduccion(self):
        return list(self._palabras_reduccion)

    @property
    def palabras_clave_contexto(self):
        return [dict(e) for e in self._palabras_contexto]

    def extraer(self, texto: str) -> ResultadoExtraccion:
        """Processes one document and returns its fragments."""
        texto = texto or ""
        cfg = self.config

        contexto, pals_contexto = "", ""
        if self._palabras_contexto:
            contexto, pals_contexto = extraer_contexto_embargado(
                texto, self._palabras_contexto,
                cfg.chars_antes_contexto, cfg.chars_despues_contexto,
                separador_parrafos=cfg.separador_contexto,
                separador_keywords=cfg.separador,
                max_distancia_corte=cfg.max_distancia_corte,
                simbolos_corte=cfg.simbolos_corte,
                delimitadores_extension=cfg.delimitadores_extension,
                max_distancia_extension=cfg.max_distancia_extension,
            )

        items_principales, items_reducidos = [], []
        for match in buscar_palabras_clave(texto, self._palabras_clave):
            chars_cfg = obtener_chars_para_categoria(
                match.get('categoria'), cfg.chars_por_categoria, cfg.chars_antes, cfg.chars_despues
            )
            if chars_cfg is None:
                # Categoría configurada con 0:0 -> se omite la extracción
                continue

            c_antes, c_despues = chars_cfg
            fragmento, inicio_frag, fin_frag = extraer_fragmento(
                texto, match['inicio'], match['fin'], c_antes, c_despues,
                max_distancia_corte=cfg.max_distancia_corte,
                simbolos_corte=cfg.simbolos_corte,
                delimitadores_extension=cfg.delimitadores_extension,
                max_distancia_extension=cfg.max_distancia_extension,
            )

            palabra_reducida = None
            if cfg.habilitar_reduccion:
                palabra_reducida = evaluar_reduccion(
                    texto, match, fragmento, fin_frag, self._patrones_reduccion,
                    cfg.categoria_reduccion, cfg.claves_requieren_numero,
                )

            item = {
                'palabra_clave': match['palabra_clave'],
                'categoria': match['categoria'],
                'inicio': match['inicio'],
                'fin': match['fin'],
                'inicio_frag': inicio_frag,
                'fin_frag': fin_frag,
                'fragmento': fragmento,
                'palabra_reducida': palabra_reducida,
            }
            (items_reducidos if palabra_reducida is not None else items_principales).append(item)

        if cfg.habilitar_agrupacion:
            principales = [_parrafo_a_fragmento(p) for p in agrupar_fragmentos_superpuestos(items_principales, texto, cfg.separador)]
            reducidos = [_parrafo_a_fragmento(p) for p in agrupar_fragmentos_superpuestos(items_reducidos, texto, cfg.separador)]
        else:
            principales = [_item_a_fragmento(i) for i in items_principales]
            reducidos = [_item_a_fragmento(i) for i in items_reducidos]

        encontradas = {f.categoria for f in principales}
        return ResultadoExtraccion(
            fragmentos_principales=principales,
            fragmentos_reducidos=reducidos,
            contexto_embargado=contexto,
            palabras_clave_contexto=pals_contexto,
            categorias_encontradas=encontradas,
            categorias_faltantes=[c for c in self._categorias if c not in encontradas],
        )

    def extraer_lote(self, textos: Iterable[str]) -> Iterator[ResultadoExtraccion]:
        """Lazily processes an iterable of documents (streaming-friendly)."""
        for texto in textos:
            yield self.extraer(texto)
