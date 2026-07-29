#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de extracción de entidades PII usando GLiNER2.

Extrae entidades de información personal identificable (PII) desde un CSV
usando el modelo fastino/gliner2-privacy-filter-PII-multi.

Entidades extraídas:
    - person
    - national_id_number / government_id / tax_id (deduplicados)
    - bank_account / account_number (deduplicados)

Uso:
    python extract_pii.py --input input.csv --output-csv output.csv --output-json output.json
"""

import argparse
import json
import logging
import sys
import time
from collections import defaultdict

# Forzar encoding UTF-8 en consolas de Windows para evitar UnicodeEncodeError en prints
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import pandas as pd
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Configuración de entidades
# ---------------------------------------------------------------------------

# Etiquetas a extraer (en inglés, el modelo las entiende aunque el texto sea en español)
ENTITY_LABELS = [
    "person",
    "national_id_number",
    "government_id",
    "tax_id",
    "bank_account",
    "account_number",
]

# Grupos de etiquetas que pueden detectar la misma entidad.
# Dentro de cada grupo, el orden define la prioridad (primer elemento = mayor prioridad).
# Cuando dos entidades del mismo grupo se solapan, se conserva la de mayor score;
# en caso de empate, se conserva la de mayor prioridad en la lista.
DEDUP_GROUPS = [
    ["national_id_number", "government_id", "tax_id"],
    ["bank_account", "account_number"],
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Funciones auxiliares
# ---------------------------------------------------------------------------


def _build_label_to_group(dedup_groups):
    """Construye un mapeo etiqueta -> (índice_grupo, prioridad_dentro_del_grupo)."""
    label_info = {}
    for group_idx, group in enumerate(dedup_groups):
        for priority, label in enumerate(group):
            label_info[label] = (group_idx, priority)
    return label_info


def _spans_overlap(start_a, end_a, start_b, end_b):
    """Retorna True si dos spans se solapan."""
    return start_a < end_b and start_b < end_a


def deduplicate_entities(entities, dedup_groups):
    """
    Deduplica entidades que pertenecen al mismo grupo de etiquetas y cuyos
    spans se solapan o cuyo texto es idéntico.

    Estrategia:
        1. Para cada par de entidades del mismo grupo con spans solapados
           o texto idéntico, conservar la de mayor score.
        2. En caso de empate de score, conservar la de mayor prioridad
           (menor índice dentro del grupo).

    Args:
        entities: lista de dicts con claves etiqueta, valor, span_inicio,
                  span_fin, score.
        dedup_groups: lista de listas de etiquetas agrupadas.

    Returns:
        Lista filtrada de entidades (sin duplicados intra-grupo).
    """
    if not entities:
        return []

    label_info = _build_label_to_group(dedup_groups)

    # Separar entidades que pertenecen a algún grupo de las que no
    grouped = defaultdict(list)  # group_idx -> [entidades]
    ungrouped = []

    for ent in entities:
        info = label_info.get(ent["etiqueta"])
        if info is not None:
            grouped[info[0]].append(ent)
        else:
            ungrouped.append(ent)

    kept = list(ungrouped)

    for group_idx, group_entities in grouped.items():
        # Ordenar por score desc, luego por prioridad asc (menor = mejor)
        group_entities.sort(
            key=lambda e: (
                -e["score"],
                label_info[e["etiqueta"]][1],
            )
        )

        # Marcar cuáles se eliminan por solapamiento con una ya conservada
        removed = set()
        for i, ent_i in enumerate(group_entities):
            if i in removed:
                continue
            for j in range(i + 1, len(group_entities)):
                if j in removed:
                    continue
                ent_j = group_entities[j]
                # Solapamiento de spans O texto idéntico
                if (
                    ent_i["valor"] == ent_j["valor"]
                    or _spans_overlap(
                        ent_i["span_inicio"],
                        ent_i["span_fin"],
                        ent_j["span_inicio"],
                        ent_j["span_fin"],
                    )
                ):
                    removed.add(j)

        for i, ent in enumerate(group_entities):
            if i not in removed:
                kept.append(ent)

    # Reordenar por posición en el texto original
    kept.sort(key=lambda e: (e["span_inicio"], e["span_fin"]))
    return kept


def extract_from_text(model, text, labels, threshold, chunk_size, chunk_overlap):
    """
    Extrae entidades de un texto usando extract_entities_long() para manejar
    textos de cualquier longitud.

    Args:
        model: instancia de GLiNER2 cargada.
        text: texto del cual extraer entidades.
        labels: lista de etiquetas a buscar.
        threshold: confianza mínima (0.0 a 1.0).
        chunk_size: tamaño de chunk en tokens de palabra.
        chunk_overlap: solapamiento entre chunks.

    Returns:
        Lista de dicts con: etiqueta, valor, span_inicio, span_fin, score.
    """
def _chunk_text_with_overlap(text, chunk_size_words=250, overlap_words=40):
    """Divide un texto en trozos (chunks) de palabras con solapamiento."""
    words = text.split()
    if len(words) <= chunk_size_words:
        yield text, 0

    step = max(1, chunk_size_words - overlap_words)
    for i in range(0, len(words), step):
        chunk_words = words[i : i + chunk_size_words]
        chunk_str = " ".join(chunk_words)
        
        # Calcular el offset aproximado en caracteres en el texto original
        # Buscamos la posición de este trozo en el texto a partir de la aproximación
        start_char = text.find(chunk_words[0]) if chunk_words else 0
        yield chunk_str, start_char


def extract_from_text(model, text, labels, threshold, chunk_size, chunk_overlap):
    """
    Extrae entidades de un texto manejando textos largos mediante chunks.
    Soporta tanto model.extract_entities_long si está disponible, como una
    estrategia propia basada en model.extract_entities.
    """
    if not text or not text.strip():
        return []

    # Si la versión de la librería soporta extract_entities_long nativamente
    if hasattr(model, "extract_entities_long"):
        try:
            result = model.extract_entities_long(
                text,
                labels,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                include_spans=True,
                include_confidence=True,
            )
            entities = []
            if isinstance(result, dict) and "entities" in result:
                raw_dict = result["entities"]
            elif isinstance(result, dict):
                raw_dict = result
            else:
                raw_dict = {}

            for label, matches in raw_dict.items():
                if not isinstance(matches, list):
                    matches = [matches]
                for match in matches:
                    if isinstance(match, dict):
                        conf = match.get("confidence", match.get("score", 1.0))
                        if conf >= threshold:
                            entities.append({
                                "etiqueta": label,
                                "valor": match.get("text", match.get("entity", "")),
                                "span_inicio": match.get("start", 0),
                                "span_fin": match.get("end", 0),
                                "score": round(conf, 4),
                            })
            return entities
        except Exception:
            pass  # Si falla, usar fallback

    # Fallback / Implementación estándar con extract_entities
    entities = []
    # Estimación simple: 1 palabra ~= 1.3 tokens de modelo
    words_per_chunk = int(chunk_size / 1.3)
    words_overlap = int(chunk_overlap / 1.3)

    # Si el texto es corto, procesar entero
    words = text.split()
    if len(words) <= words_per_chunk:
        chunks = [(text, 0)]
    else:
        chunks = list(_chunk_text_with_overlap(text, words_per_chunk, words_overlap))

    seen_spans = set()

    for chunk_str, _ in chunks:
        try:
            # GLiNER2 extract_entities / extract
            if hasattr(model, "extract_entities"):
                res = model.extract_entities(chunk_str, labels)
            elif hasattr(model, "extract"):
                res = model.extract(chunk_str, labels)
            elif callable(model):
                res = model(chunk_str, labels)
            else:
                res = {}
        except Exception as e:
            logger.warning("Error al procesar chunk: %s", e)
            continue

        # Normalizar respuesta según formato de GLiNER2 / GLiNER
        # GLiNER2 puede devolver {'entities': {'person': ['Juan'], ...}} o listas de dicts
        matches_list = []
        if isinstance(res, dict):
            if "entities" in res:
                res = res["entities"]
            
            for label, vals in res.items():
                if label not in labels:
                    continue
                if isinstance(vals, list):
                    for v in vals:
                        if isinstance(v, dict):
                            matches_list.append((label, v.get("text", v.get("entity", "")), v.get("score", 1.0), v.get("start", -1), v.get("end", -1)))
                        elif isinstance(v, str):
                            matches_list.append((label, v, 1.0, -1, -1))
                elif isinstance(vals, str):
                    matches_list.append((label, vals, 1.0, -1, -1))
        elif isinstance(res, list):
            for item in res:
                if isinstance(item, dict):
                    lbl = item.get("label", item.get("entity_type", ""))
                    val = item.get("text", item.get("entity", ""))
                    score = item.get("score", item.get("confidence", 1.0))
                    st = item.get("start", -1)
                    en = item.get("end", -1)
                    if lbl in labels:
                        matches_list.append((lbl, val, score, st, en))

        for lbl, val, score, st, en in matches_list:
            if not val or score < threshold:
                continue
            
            # Re-calcular posición en texto original si no viene dada
            if st == -1 or en == -1:
                st = text.find(val)
                if st != -1:
                    en = st + len(val)
                else:
                    st, en = 0, len(val)

            key = (lbl, val, st, en)
            if key not in seen_spans:
                seen_spans.add(key)
                entities.append({
                    "etiqueta": lbl,
                    "valor": val,
                    "span_inicio": st,
                    "span_fin": en,
                    "score": round(score, 4),
                })

    return entities


def process_csv(model, args):
    """
    Procesa el CSV de entrada fila por fila, extrae entidades y genera
    los archivos de salida (CSV + JSON).

    Args:
        model: instancia de GLiNER2 cargada.
        args: argumentos parseados de la CLI.

    Returns:
        DataFrame con los resultados.
    """
    logger.info("Leyendo CSV de entrada: %s", args.input)
    df = pd.read_csv(args.input, sep=args.separator, encoding="utf-8")
    logger.info("Filas en el CSV: %d", len(df))

    if args.text_column not in df.columns:
        logger.error(
            "La columna '%s' no existe en el CSV. Columnas disponibles: %s",
            args.text_column,
            list(df.columns),
        )
        sys.exit(1)

    results = []
    total_entities_raw = 0
    total_entities_dedup = 0
    numero_archivo = 0
    id_anterior = None

    for _, row in tqdm(df.iterrows(), total=len(df), desc="Procesando registros"):
        # Asignar numero_archivo: cambia cada vez que cambia el id
        current_id = row.get("id", "")
        if current_id != id_anterior:
            numero_archivo += 1
            id_anterior = current_id

        text = str(row[args.text_column]) if pd.notna(row[args.text_column]) else ""

        # Extraer entidades
        raw_entities = extract_from_text(
            model,
            text,
            ENTITY_LABELS,
            args.threshold,
            args.chunk_size,
            args.chunk_overlap,
        )
        total_entities_raw += len(raw_entities)

        # Deduplicar
        clean_entities = deduplicate_entities(raw_entities, DEDUP_GROUPS)
        total_entities_dedup += len(clean_entities)

        # Construir registros de salida
        for entity in clean_entities:
            results.append(
                {
                    "numero_archivo": numero_archivo,
                    "id": row.get("id", ""),
                    "nombre_archivo": row.get("nombre_archivo", ""),
                    "clasificacion": row.get("clasificacion", ""),
                    "texto_limpio": text,
                    "etiqueta": entity["etiqueta"],
                    "valor": entity["valor"],
                    "span_inicio": entity["span_inicio"],
                    "span_fin": entity["span_fin"],
                    "score": entity["score"],
                }
            )

    logger.info(
        "Entidades extraídas: %d (antes de dedup) -> %d (después de dedup)",
        total_entities_raw,
        total_entities_dedup,
    )

    output_df = pd.DataFrame(results)

    # Si no hay resultados, crear DataFrame vacío con las columnas esperadas
    if output_df.empty:
        output_df = pd.DataFrame(
            columns=[
                "numero_archivo",
                "id",
                "nombre_archivo",
                "clasificacion",
                "texto_limpio",
                "etiqueta",
                "valor",
                "span_inicio",
                "span_fin",
                "score",
            ]
        )

    return output_df


def save_outputs(output_df, args):
    """Guarda los resultados en CSV y JSON."""
    # CSV
    output_df.to_csv(
        args.output_csv, sep=";", index=False, encoding="utf-8"
    )
    logger.info("CSV guardado en: %s (%d filas)", args.output_csv, len(output_df))

    # JSON
    records = output_df.to_dict(orient="records")
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info("JSON guardado en: %s", args.output_json)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extrae entidades PII de un CSV usando GLiNER2.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python extract_pii.py --input datos.csv
  python extract_pii.py --input datos.csv --threshold 0.7 --device cuda
  python extract_pii.py --input datos.csv --text-column otra_columna --separator ","
        """,
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Ruta al CSV de entrada.",
    )
    parser.add_argument(
        "--output-csv",
        default="output.csv",
        help="Ruta del CSV de salida (default: output.csv).",
    )
    parser.add_argument(
        "--output-json",
        default="output.json",
        help="Ruta del JSON de salida (default: output.json).",
    )
    parser.add_argument(
        "--text-column",
        default="texto_limpio",
        help="Nombre de la columna con el texto a procesar (default: texto_limpio).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Confianza mínima para aceptar una entidad, entre 0.0 y 1.0 (default: 0.5).",
    )
    parser.add_argument(
        "--separator",
        default=";",
        help="Separador del CSV de entrada (default: ;).",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        choices=["cpu", "cuda"],
        help="Dispositivo de inferencia: cpu o cuda (default: cpu).",
    )
    parser.add_argument(
        "--model",
        default="fastino/gliner2-privacy-filter-PII-multi",
        help="Modelo de HuggingFace a usar (default: fastino/gliner2-privacy-filter-PII-multi).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=384,
        help="Tamaño de chunk en tokens para textos largos (default: 384).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=64,
        help="Solapamiento entre chunks en tokens (default: 64).",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    args = parse_args()

    logger.info("=" * 60)
    logger.info("Extracción de entidades PII con GLiNER2")
    logger.info("=" * 60)
    logger.info("Modelo: %s", args.model)
    logger.info("Dispositivo: %s", args.device)
    logger.info("Threshold: %.2f", args.threshold)
    logger.info("Columna de texto: %s", args.text_column)
    logger.info("Chunk size: %d | Chunk overlap: %d", args.chunk_size, args.chunk_overlap)
    logger.info("Input: %s", args.input)
    logger.info("Output CSV: %s", args.output_csv)
    logger.info("Output JSON: %s", args.output_json)
    logger.info("-" * 60)

    # Cargar modelo
    logger.info("Cargando modelo...")
    start_load = time.time()

    from gliner2 import GLiNER2

    model = GLiNER2.from_pretrained(args.model)

    # Mover a GPU si corresponde
    if args.device == "cuda":
        import torch

        if torch.cuda.is_available():
            model = model.to("cuda")
            logger.info("Modelo movido a GPU (CUDA)")
        else:
            logger.warning("CUDA no disponible, usando CPU")

    load_time = time.time() - start_load
    logger.info("Modelo cargado en %.1f segundos", load_time)

    # Procesar CSV
    start_process = time.time()
    output_df = process_csv(model, args)
    process_time = time.time() - start_process

    # Guardar resultados
    save_outputs(output_df, args)

    # Resumen final
    logger.info("=" * 60)
    logger.info("RESUMEN")
    logger.info("Tiempo de carga del modelo: %.1f s", load_time)
    logger.info("Tiempo de procesamiento: %.1f s", process_time)
    logger.info("Tiempo total: %.1f s", load_time + process_time)
    logger.info("Total entidades en output: %d", len(output_df))
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
