"""
ejecutar.py - Extracción de datos en producción sobre documentos judiciales usando DSPy.

Uso:
    python ejecutar.py frag_con_texto.csv
    python ejecutar.py frag_con_texto.csv --prog programas/embargo_optimizado.json --output output/salida.csv
    python ejecutar.py frag_con_texto.csv --limit 5
    python ejecutar.py frag_con_texto.csv --reset
"""

import os
import sys
import time
import argparse
import logging
from typing import List, Dict, Any
from tqdm import tqdm

from src.utils import (
    configurar_lm,
    setup_logging,
    cargar_config,
    ruta_checkpoint,
    cargar_checkpoint,
    guardar_checkpoint,
    expandir_embargados,
    escribir_csv_salida,
)
from src.extractor import ExtraerEmbargo
from src.dataset import cargar_textos_completos


def leer_documentos_produccion(ruta_csv: str, columna_texto: str = "texto_completo") -> List[Dict[str, Any]]:
    """
    Lee el archivo CSV de producción y retorna una lista de documentos únicos (por 'id')
    con metadatos y el texto a analizar.
    """
    mapa = cargar_textos_completos(ruta_csv)
    if not mapa:
        raise ValueError(f"No se pudieron cargar documentos desde: {ruta_csv}")

    documentos = []
    for doc_id, datos in mapa.items():
        documentos.append({
            "id": doc_id,
            "numero_archivo": datos["numero_archivo"],
            "nombre": datos["nombre"],
            "texto": datos["texto_completo"],
        })

    return documentos


def main():
    parser = argparse.ArgumentParser(description="Extraer datos de embargos judiciales en producción.")
    parser.add_argument("input_csv", nargs="?", default=None, help="Ruta al CSV de entrada (ej: frag_con_texto.csv)")
    parser.add_argument("--config", default="config/embargo.yaml", help="Ruta al archivo YAML de configuración")
    parser.add_argument("--prog", default=None, help="Ruta al programa DSPy compilado")
    parser.add_argument("--output", default=None, help="Ruta al CSV de salida")
    parser.add_argument("--columna", default=None, help="Columna que contiene el texto del documento")
    parser.add_argument("--limit", type=int, default=None, help="Procesar solo los primeros N documentos")
    parser.add_argument("--reset", action="store_true", help="Ignorar checkpoint existente y procesar desde cero")
    parser.add_argument("--batch-size", type=int, default=5, help="Frecuencia de guardado del checkpoint")
    args = parser.parse_args()

    tiempo_inicio = time.time()
    logger = setup_logging()
    cfg = cargar_config(args.config)

    # Rutas y parámetros
    ruta_input = args.input_csv or cfg.get("datos", {}).get("frag_con_texto", "frag_con_texto.csv")
    ruta_salida = args.output or cfg.get("rutas", {}).get("output_default", "output/extraccion_embargos.csv")
    ruta_prog = args.prog or cfg.get("rutas", {}).get("programa_compilado", "programas/embargo_optimizado.json")
    columna_texto = args.columna or cfg.get("datos", {}).get("campo_produccion", "texto_completo")
    max_reintentos = cfg.get("extraccion", {}).get("max_reintentos", 2)

    logger.info("=== INICIANDO EXTRACCIÓN EN PRODUCCIÓN ===")
    logger.info(f"Input CSV: {ruta_input}")
    logger.info(f"Output CSV: {ruta_salida}")
    logger.info(f"Columna de texto: {columna_texto}")

    # 1. Configurar LLM
    llm_cfg = cfg.get("llm", {})
    configurar_lm(
        api_base=llm_cfg.get("api_base", "http://localhost:1234/v1"),
        model=llm_cfg.get("model", "openai/local-model"),
        temperature=llm_cfg.get("temperature", 0.0),
        max_tokens=llm_cfg.get("max_tokens", 1500),
        api_key=llm_cfg.get("api_key", "local")
    )

    # 2. Cargar documentos únicos
    docs = leer_documentos_produccion(ruta_input, columna_texto=columna_texto)
    logger.info(f"Total de documentos únicos por ID encontrados: {len(docs)}")

    if args.limit and args.limit > 0:
        docs = docs[:args.limit]
        logger.info(f"Límite aplicado: procesando únicamente {len(docs)} documentos")

    # 3. Inicializar módulo DSPy
    cot = cfg.get("extraccion", {}).get("cot", False)
    max_chars = cfg.get("extraccion", {}).get("max_chars", 12000)
    extractor = ExtraerEmbargo(cot=cot, max_chars=max_chars)

    if os.path.exists(ruta_prog):
        logger.info(f"Cargando programa compilado desde: {ruta_prog}")
        extractor.cargar(ruta_prog)
    else:
        logger.warning(
            f"Programa compilado no encontrado en '{ruta_prog}'. "
            "Ejecutando en modo Zero-Shot base."
        )

    # 4. Checkpoint
    chk_path = ruta_checkpoint(ruta_salida)
    if args.reset and os.path.exists(chk_path):
        logger.info(f"Opción --reset activa. Eliminando checkpoint previo: {chk_path}")
        os.remove(chk_path)

    checkpoint = cargar_checkpoint(chk_path) if not args.reset else {}

    # Filtrar documentos pendientes
    docs_pendientes = [d for d in docs if str(d["id"]) not in checkpoint]
    logger.info(f"Documentos ya procesados: {len(checkpoint)} | Pendientes: {len(docs_pendientes)}")

    # 5. Extracción por documento
    docs_nuevos = 0
    pbar = tqdm(docs_pendientes, desc="Extrayendo datos", unit="doc")

    for d in pbar:
        doc_id = str(d["id"])
        texto = d["texto"]

        pbar.set_postfix({"id": doc_id})

        resultado_dict = extractor.extraer_dict(texto, max_reintentos=max_reintentos)
        checkpoint[doc_id] = resultado_dict
        docs_nuevos += 1

        if docs_nuevos % args.batch_size == 0:
            guardar_checkpoint(chk_path, checkpoint)

    # Guardar checkpoint final
    if docs_nuevos > 0:
        guardar_checkpoint(chk_path, checkpoint)

    # 6. Post-procesamiento y expansión de filas múltiples
    logger.info("Realizando post-procesamiento y expansión de embargados múltiples...")
    filas_finales = []
    
    # Mapa rápido de metadatos de documentos
    meta_map = {str(d["id"]): {"numero_archivo": d["numero_archivo"], "id": d["id"], "nombre": d["nombre"]} for d in docs}

    for doc_id, res in checkpoint.items():
        if doc_id not in meta_map:
            continue
        metadatos = meta_map[doc_id]
        filas_expandidas = expandir_embargados(res, metadatos)
        filas_finales.extend(filas_expandidas)

    # 7. Escritura de salida
    escribir_csv_salida(ruta_salida, filas_finales)

    duracion = time.time() - tiempo_inicio
    logger.info(
        f"=== EXTRACCIÓN COMPLETADA CON ÉXITO ===\n"
        f"  Total documentos analizados: {len(checkpoint)}\n"
        f"  Total filas expandidas generadas: {len(filas_finales)}\n"
        f"  Archivo guardado: {ruta_salida}\n"
        f"  Tiempo transcurrido: {duracion:.2f} s ({duracion/60:.2f} min)"
    )


if __name__ == "__main__":
    main()
