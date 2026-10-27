"""
CLI / batch CSV adapter.

Reads an input CSV, runs every document through ``ExtraccionFragmento`` and
writes the outputs inside a timestamped folder:
  - main CSV (fragments)
  - extra CSV (reduced fragments, only when reduction is enabled)
  - ``<main>_sin_match.txt`` (documents with missing categories)
"""
import argparse
import csv
import logging
import os
import sys
from contextlib import ExitStack
from datetime import datetime

from .extractor import ExtraccionFragmento
from .loaders import cargar_palabras_clave, cargar_palabras_reduccion
from .models import ExtractorConfig

COLUMNAS_PRINCIPAL = [
    'numero_archivo', 'id', 'nombre', 'contador_interno', 'palabra_clave', 'categoria',
    'fragmento', 'contexto_embargado', 'palabra_clave_contexto', 'posicion_inicio',
    'posicion_fin', 'inicio_fragmento', 'fin_fragmento', 'texto_completo',
]

COLUMNAS_EXTRA = [
    'numero_archivo', 'id', 'nombre', 'contador_interno', 'palabra_clave', 'categoria',
    'fragmento', 'posicion_inicio', 'posicion_fin', 'inicio_fragmento', 'fin_fragmento',
    'palabra_reduccion', 'texto_completo',
]


class ErrorProcesamiento(Exception):
    """Fatal error while processing the input CSV."""


def desescapar_texto(texto):
    """
    Limpia y desescapa el texto proveniente de un campo CSV.
    """
    if not texto:
        return ""

    # Reemplazar saltos de línea de Windows a estándar de Unix
    texto = texto.replace('\r\n', '\n')

    # Convertir comillas dobles internas escapadas ("" -> ")
    texto_desescapado = texto.replace('""', '"')

    # Si el campo está envuelto en comillas dobles, removerlas
    stripped = texto_desescapado.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        texto_desescapado = stripped[1:-1]

    return texto_desescapado


def buscar_indice_columna(headers, nombre_esperado, default_index):
    """
    Busca de forma flexible e insensible a mayúsculas el índice de una columna.
    """
    nombre_esperado_lower = nombre_esperado.lower()
    for idx, header in enumerate(headers):
        if header.strip().lower() == nombre_esperado_lower:
            return idx
    for idx, header in enumerate(headers):
        if nombre_esperado_lower in header.strip().lower():
            return idx
    return default_index


def detectar_delimitador(primera_linea):
    """Detects ';', '\\t' or ',' from the header line (default ';')."""
    if ';' in primera_linea and primera_linea.count(';') > primera_linea.count(','):
        return ';'
    if '\t' in primera_linea and primera_linea.count('\t') > primera_linea.count(','):
        return '\t'
    if ',' in primera_linea:
        return ','
    return ';'


def _cargar_opcional(ruta, loader, descripcion, consecuencia):
    if not ruta:
        return []
    try:
        return loader(ruta)
    except FileNotFoundError:
        print(f"Advertencia: El archivo de {descripcion} '{ruta}' no existe. {consecuencia}", file=sys.stderr)
        return []


def _celda(row, idx):
    return row[idx].strip() if (idx != -1 and idx < len(row)) else ""


def generar_carpeta_ejecucion(dir_output):
    """
    Generates a unique execution directory under dir_output.
    Uses 'fragmento_YYYY_MM_DD_HH_MM_SS'. If it already exists (e.g. rapid
    successive executions in a pipeline), appends a unique numeric counter.
    """
    base_nombre = datetime.now().strftime("fragmento_%Y_%m_%d_%H_%M_%S")
    carpeta = os.path.join(dir_output, base_nombre)
    if not os.path.exists(carpeta):
        os.makedirs(carpeta, exist_ok=True)
        return carpeta

    contador = 1
    while True:
        carpeta_candidata = os.path.join(dir_output, f"{base_nombre}_{contador}")
        if not os.path.exists(carpeta_candidata):
            os.makedirs(carpeta_candidata, exist_ok=True)
            return carpeta_candidata
        contador += 1


def procesar_csv(ruta_csv, columna_texto, ruta_palabras, chars_antes, chars_despues, ruta_salida,
                 ruta_reduccion=None, ruta_extra="extra.csv", dir_output="output", nombre_param=None,
                 renumerar=False, agrupar=True, separador=" | ", ruta_palabras_contexto=None,
                 chars_antes_contexto=200, chars_despues_contexto=200, chars_por_categoria=None,
                 max_distancia_corte=0, simbolos_corte="", max_distancia_extension=0,
                 delimitadores_extension="", habilitar_reduccion=True):
    """
    Processes a CSV file end to end. Returns a summary dict.
    Raises ``ErrorProcesamiento`` on fatal input errors.
    """
    try:
        palabras_clave = cargar_palabras_clave(ruta_palabras)
    except FileNotFoundError as exc:
        raise ErrorProcesamiento(f"No se pudieron cargar palabras clave ({exc}).") from exc
    if not palabras_clave:
        raise ErrorProcesamiento("No se pudieron cargar palabras clave. Abortando.")

    if not os.path.exists(ruta_csv):
        raise ErrorProcesamiento(f"El archivo de entrada '{ruta_csv}' no existe.")

    # Crear carpeta de salida única para la ejecución
    carpeta_ejecucion = generar_carpeta_ejecucion(dir_output)

    nombre_salida = os.path.basename(ruta_salida) if ruta_salida else "output_embargos.csv"
    ruta_salida_final = os.path.join(carpeta_ejecucion, nombre_salida)
    nombre_extra = os.path.basename(ruta_extra) if ruta_extra else "extra.csv"
    ruta_extra_final = os.path.join(carpeta_ejecucion, nombre_extra)

    palabras_reduccion = []
    if habilitar_reduccion:
        palabras_reduccion = _cargar_opcional(
            ruta_reduccion, cargar_palabras_reduccion, "reducción", "Se procesará sin reducción."
        )
        if palabras_reduccion:
            print(f"Cargadas {len(palabras_reduccion)} palabras/patrones de reducción desde '{ruta_reduccion}'.")
    else:
        print("Reducción de falsos positivos desactivada.")

    palabras_contexto = _cargar_opcional(
        ruta_palabras_contexto, cargar_palabras_clave, "palabras clave de contexto",
        "contexto_embargado quedará vacío."
    )
    if palabras_contexto:
        print(f"Cargadas {len(palabras_contexto)} palabras clave de contexto_embargado desde '{ruta_palabras_contexto}'.")

    config = ExtractorConfig(
        chars_antes=chars_antes,
        chars_despues=chars_despues,
        habilitar_reduccion=habilitar_reduccion,
        habilitar_agrupacion=agrupar,
        separador=separador,
        chars_por_categoria=chars_por_categoria,
        delimitadores_extension=delimitadores_extension,
        max_distancia_extension=max_distancia_extension,
        simbolos_corte=simbolos_corte,
        max_distancia_corte=max_distancia_corte,
        chars_antes_contexto=chars_antes_contexto,
        chars_despues_contexto=chars_despues_contexto,
    )
    _imprimir_config(config)

    extractor = ExtraccionFragmento(
        palabras_clave, config=config,
        palabras_reduccion=palabras_reduccion,
        palabras_clave_contexto=palabras_contexto,
    )
    categorias = extractor.categorias

    print(f"Cargadas {len(palabras_clave)} palabras clave en {len(categorias)} categorías: {', '.join(categorias)}")
    print(f"Carpeta de salida: '{carpeta_ejecucion}'")
    print(f"Procesando '{ruta_csv}'...")

    stats = {
        'documentos_procesados': 0, 'documentos_con_match': 0, 'registros_creados': 0,
        'registros_vacios': 0, 'registros_extra': 0, 'registros_extra_vacios': 0,
    }
    # (num_archivo, id, {categorias_encontradas}) de documentos con categorías faltantes
    docs_faltantes = []

    with open(ruta_csv, mode='r', encoding='utf-8-sig', newline='') as f_in:
        primera_linea = f_in.readline()
        f_in.seek(0)
        reader = csv.reader(f_in, delimiter=detectar_delimitador(primera_linea))
        headers = next(reader, None)
        if not headers:
            raise ErrorProcesamiento("El archivo CSV está vacío.")

        cols = _resolver_columnas(headers, columna_texto, nombre_param, renumerar)

        with ExitStack() as stack:
            f_out = stack.enter_context(open(ruta_salida_final, mode='w', encoding='utf-8-sig', newline=''))
            writer = csv.writer(f_out, delimiter=';')
            writer.writerow(COLUMNAS_PRINCIPAL)

            writer_extra = None
            if habilitar_reduccion:
                f_extra = stack.enter_context(open(ruta_extra_final, mode='w', encoding='utf-8-sig', newline=''))
                writer_extra = csv.writer(f_extra, delimiter=';')
                writer_extra.writerow(COLUMNAS_EXTRA)

            for row in reader:
                if not row:
                    continue
                stats['documentos_procesados'] += 1
                n_doc = stats['documentos_procesados']

                if cols['secuencial']:
                    num_archivo = str(n_doc)
                else:
                    num_archivo = _celda(row, cols['numero']) or str(n_doc)
                doc_id = _celda(row, cols['id'])
                nombre = cols['nombre_fijo'] if cols['nombre_fijo'] is not None else _celda(row, cols['nombre'])
                texto = desescapar_texto(row[cols['texto']] if cols['texto'] < len(row) else "")

                res = extractor.extraer(texto)

                if res.fragmentos_principales:
                    for idx, f in enumerate(res.fragmentos_principales, start=1):
                        writer.writerow([
                            num_archivo, doc_id, nombre, idx, f.palabra_clave, f.categoria, f.fragmento,
                            res.contexto_embargado, res.palabras_clave_contexto,
                            f.posicion_inicio, f.posicion_fin, f.inicio_fragmento, f.fin_fragmento, texto,
                        ])
                    stats['registros_creados'] += len(res.fragmentos_principales)
                    stats['documentos_con_match'] += 1
                else:
                    # Fila vacía para preservar el (numero_archivo, id) en el output
                    writer.writerow([num_archivo, doc_id, nombre, 0, "", "", "",
                                     res.contexto_embargado, res.palabras_clave_contexto,
                                     "", "", "", "", texto])
                    stats['registros_vacios'] += 1

                if writer_extra:
                    if res.fragmentos_reducidos:
                        for idx, f in enumerate(res.fragmentos_reducidos, start=1):
                            writer_extra.writerow([
                                num_archivo, doc_id, nombre, idx, f.palabra_clave, f.categoria, f.fragmento,
                                f.posicion_inicio, f.posicion_fin, f.inicio_fragmento, f.fin_fragmento,
                                f.palabra_reduccion, texto,
                            ])
                        stats['registros_extra'] += len(res.fragmentos_reducidos)
                    else:
                        writer_extra.writerow([num_archivo, doc_id, nombre, 0,
                                               "", "", "", "", "", "", "", "", texto])
                        stats['registros_extra_vacios'] += 1

                if res.categorias_faltantes:
                    docs_faltantes.append((num_archivo, doc_id, res.categorias_encontradas))

    # Guardar documentos con categorías faltantes en un archivo TXT
    base_salida = os.path.splitext(nombre_salida)[0]
    ruta_sin_match = os.path.join(carpeta_ejecucion, f"{base_salida}_sin_match.txt")
    with open(ruta_sin_match, 'w', encoding='utf-8') as f_sin:
        f_sin.write("\t".join(["numero_archivo", "id"] + [cat.lower() for cat in categorias]) + "\n")
        for num, did, cats_encontradas in docs_faltantes:
            valores = [num, did] + ["SI" if cat in cats_encontradas else "NO" for cat in categorias]
            f_sin.write("\t".join(valores) + "\n")

    resumen = dict(stats)
    resumen.update({
        'carpeta_ejecucion': carpeta_ejecucion,
        'ruta_salida': ruta_salida_final,
        'ruta_extra': ruta_extra_final if habilitar_reduccion else None,
        'ruta_sin_match': ruta_sin_match,
        'documentos_con_categorias_faltantes': len(docs_faltantes),
    })
    _imprimir_resumen(resumen, bool(palabras_reduccion))
    return resumen


def _resolver_columnas(headers, columna_texto, nombre_param, renumerar):
    idx_numero = buscar_indice_columna(headers, 'numero_archivo', -1)
    idx_id = buscar_indice_columna(headers, 'id', -1)
    if idx_id == -1:
        idx_id = 0

    # Columna 'nombre' o valor constante parametrizado
    idx_nombre = -1
    nombre_fijo = None
    if nombre_param is not None:
        for idx, h in enumerate(headers):
            if h.strip().lower() == nombre_param.strip().lower():
                idx_nombre = idx
                break
        if idx_nombre == -1:
            nombre_fijo = nombre_param
    else:
        idx_nombre = buscar_indice_columna(headers, 'nombre', -1)

    idx_texto = buscar_indice_columna(headers, columna_texto, -1)
    if idx_texto == -1 or idx_texto >= len(headers):
        # Fallback: texto_limpio o texto
        idx_texto = buscar_indice_columna(headers, 'texto_limpio', -1)
        if idx_texto == -1:
            idx_texto = buscar_indice_columna(headers, 'texto', -1)
        if idx_texto == -1 or idx_texto >= len(headers):
            raise ErrorProcesamiento(f"No se encontró la columna de texto '{columna_texto}' en el CSV.")

    secuencial = renumerar or idx_numero == -1
    if secuencial:
        print("Campo 'numero_archivo': numeración secuencial iniciando en 1 para cada archivo.")
    else:
        print(f"Campo 'numero_archivo': extraído de la columna '{headers[idx_numero]}'.")

    if nombre_fijo is not None:
        print(f"Campo 'nombre': valor fijo parametrizado '{nombre_fijo}'.")
    elif idx_nombre != -1:
        print(f"Campo 'nombre': extraído de la columna '{headers[idx_nombre]}'.")
    else:
        print("Campo 'nombre': no especificado ni presente en el CSV (quedará vacío).")

    return {'numero': idx_numero, 'id': idx_id, 'nombre': idx_nombre, 'nombre_fijo': nombre_fijo,
            'texto': idx_texto, 'secuencial': secuencial}


def _imprimir_config(config):
    if config.delimitadores_extension:
        delims = ', '.join(repr(d) for d in config.delimitadores_extension)
        lim = f"máx {config.max_distancia_extension} chars" if config.max_distancia_extension > 0 else "sin límite de distancia"
        print(f"Extensión de fragmentos activada: delimitadores [{delims}], {lim}")
    if config.max_distancia_corte > 0 and config.simbolos_corte:
        simbs = ', '.join(repr(s) for s in config.simbolos_corte)
        print(f"Corte de fragmentos activado: símbolos/secuencias [{simbs}], máx {config.max_distancia_corte} chars hacia adentro")
    if config.chars_por_categoria:
        detalles = [
            f"{k}: omitir (0:0)" if v == (0, 0) else f"{k}: {v[0]} antes / {v[1]} después"
            for k, v in config.chars_por_categoria.items()
        ]
        print(f"Caracteres configurados por categoría: {', '.join(detalles)}")
    if not config.habilitar_agrupacion:
        print("Agrupación de fragmentos superpuestos desactivada.")


def _imprimir_resumen(r, hay_patrones_reduccion):
    print("\n--- Resumen de ejecución ---")
    print(f"Carpeta de salida: '{r['carpeta_ejecucion']}'")
    print(f"Documentos procesados: {r['documentos_procesados']}")
    print(f"Documentos con coincidencias (en salida principal): {r['documentos_con_match']}")
    print(f"Documentos sin coincidencias (fila vacía en salida principal): {r['registros_vacios']}")
    print(f"Documentos con al menos una categoría faltante: {r['documentos_con_categorias_faltantes']}")
    print(f"Registros de fragmentos con coincidencia: {r['registros_creados']}")
    print(f"Total filas en salida principal: {r['registros_creados'] + r['registros_vacios']}")
    print(f"Archivo de salida principal guardado en: '{r['ruta_salida']}'")
    if hay_patrones_reduccion:
        print(f"Registros de fragmentos reducidos (con coincidencia): {r['registros_extra']}")
        print(f"Documentos sin fragmentos reducidos (fila vacía en extra): {r['registros_extra_vacios']}")
        print(f"Total filas en archivo extra: {r['registros_extra'] + r['registros_extra_vacios']}")
        print(f"Archivo de fragmentos reducidos guardado en: '{r['ruta_extra']}'")
    if r['documentos_con_categorias_faltantes']:
        print(f"Documentos con categorías faltantes guardados en: '{r['ruta_sin_match']}'")


def construir_parser():
    parser = argparse.ArgumentParser(
        description="Extrae fragmentos de texto a partir de un CSV usando palabras clave."
    )
    parser.add_argument("input", help="Ruta al CSV de entrada")
    parser.add_argument("-o", "--output", default="output_embargos.csv",
                        help="Nombre del CSV de salida principal (default: output_embargos.csv)")
    parser.add_argument("--output-dir", default="output",
                        help="Directorio base donde se guardará la carpeta con timestamp de cada ejecución (default: output)")
    parser.add_argument("-c", "--columna", default="texto_limpio",
                        help="Nombre de la columna del CSV que contiene el texto (default: texto_limpio)")
    parser.add_argument("-k", "--keywords", default="palabras_clave.txt",
                        help="Ruta al archivo de palabras clave (default: palabras_clave.txt)")
    parser.add_argument("-r", "--reduccion", default=None,
                        help="Ruta al archivo TXT con palabras clave de reducción para separar fragmentos a un extra.csv (opcional)")
    parser.add_argument("--extra", default="extra.csv",
                        help="Nombre del CSV donde guardar los fragmentos reducidos/separados (default: extra.csv)")
    parser.add_argument("--sin-reduccion", action="store_true",
                        help="Desactiva por completo la reducción de falsos positivos (no se genera el CSV extra)")
    parser.add_argument("-n", "--nombre", default=None,
                        help="Valor para el campo 'nombre' en los CSV de salida o nombre de la columna en el CSV de entrada que lo contiene (opcional, default: detecta columna 'nombre' o vacío)")
    parser.add_argument("--renumerar", action="store_true",
                        help="Fuerza a que 'numero_archivo' sea siempre secuencial (1, 2, 3...) según el orden de procesamiento, ignorando el valor de la columna si existe")
    parser.add_argument("-a", "--antes", type=int, default=200,
                        help="Caracteres a extraer antes de la coincidencia (default: 200)")
    parser.add_argument("-p", "--despues", type=int, default=200,
                        help="Caracteres a extraer después de la coincidencia (default: 200)")
    parser.add_argument("--sin-agrupar", action="store_true",
                        help="Desactiva la agrupación de fragmentos superpuestos en párrafos (mantiene 1 fila por coincidencia individual)")
    parser.add_argument("--separador", default=" | ",
                        help="Separador usado para unir múltiples palabras clave o categorías en un párrafo agrupado (default: ' | ')")
    parser.add_argument("--chars-categoria", default=None,
                        help="Configuración de caracteres antes y después por categoría en formato 'Cat1:antes:despues,Cat2:antes:despues'. 0:0 omite la categoría (ej: 'Datos_Embargado:200:300,Montos:50:100,Cuenta_depositar:0:0')")
    parser.add_argument("--keywords-contexto", default=None,
                        help="Ruta al archivo TXT de palabras clave para extraer contexto_embargado del texto completo (opcional)")
    parser.add_argument("--antes-contexto", type=int, default=200,
                        help="Caracteres antes de la coincidencia para contexto_embargado (default: 200)")
    parser.add_argument("--despues-contexto", type=int, default=200,
                        help="Caracteres después de la coincidencia para contexto_embargado (default: 200)")
    parser.add_argument("--distancia-corte", type=int, default=0,
                        help="Cantidad máxima de caracteres hacia adentro del fragmento para buscar un símbolo de corte. 0 desactiva esta búsqueda (default: 0)")
    parser.add_argument("--simbolos-corte", default="",
                        help="Símbolos utilizados para recortar el fragmento (ej. ',;.'). Si no encuentra el símbolo, o si está vacío, usa el corte por palabra original (default: '')")
    parser.add_argument("--distancia-extension", type=int, default=0,
                        help="Cantidad máxima de caracteres hacia afuera del fragmento para buscar delimitadores de extensión. 0 significa sin límite de distancia (default: 0)")
    parser.add_argument("--delimitadores-extension", default="",
                        help="Delimitadores para extender el fragmento hacia afuera (ej. '. ', '\\n'). Separados por coma o barra vertical. Vacío desactiva la extensión (default: '')")
    return parser


def main(argv=None):
    logging.basicConfig(level=logging.WARNING, format="Advertencia: %(message)s", stream=sys.stderr)
    args = construir_parser().parse_args(argv)
    try:
        procesar_csv(
            ruta_csv=args.input,
            columna_texto=args.columna,
            ruta_palabras=args.keywords,
            chars_antes=args.antes,
            chars_despues=args.despues,
            ruta_salida=args.output,
            ruta_reduccion=args.reduccion,
            ruta_extra=args.extra,
            dir_output=args.output_dir,
            nombre_param=args.nombre,
            renumerar=args.renumerar,
            agrupar=not args.sin_agrupar,
            separador=args.separador,
            ruta_palabras_contexto=args.keywords_contexto,
            chars_antes_contexto=args.antes_contexto,
            chars_despues_contexto=args.despues_contexto,
            chars_por_categoria=args.chars_categoria,
            max_distancia_corte=args.distancia_corte,
            simbolos_corte=args.simbolos_corte,
            max_distancia_extension=args.distancia_extension,
            delimitadores_extension=args.delimitadores_extension,
            habilitar_reduccion=not args.sin_reduccion,
        )
    except (ErrorProcesamiento, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
