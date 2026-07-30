#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de extracción de entidades PII multi-modelo usando GLiNER y GLiNER2.

Permite ejecutar individualmente o en conjunto los modelos:
    - fastino/gliner2-privacy-filter-PII-multi (gliner2)
    - urchade/gliner_multi_pii-v1 (pii_v1)
    - gliner-community/gliner_large-v2.5 (large_v25)

Uso:
    python extract_pii_v2.py --input input.csv --model all --device cuda
"""

import argparse
import json
import logging
import os
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
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registro de Modelos y Mapeo de Etiquetas
# ---------------------------------------------------------------------------

MODEL_REGISTRY = {
    "gliner2": {
        "hf_name": "fastino/gliner2-privacy-filter-PII-multi",
        "library": "gliner2",
        "prefix": "gliner2",
        "labels": ["person", "national_id_number", "government_id", "tax_id", "bank_account", "account_number"]
    },
    "pii_v1": {
        "hf_name": "urchade/gliner_multi_pii-v1",
        "library": "gliner",
        "prefix": "pii_v1",
        "labels": ["person", "national id number", "tax identification number", "bank account number", "social security number"]
    },
    "large_v25": {
        "hf_name": "gliner-community/gliner_large-v2.5",
        "library": "gliner",
        "prefix": "large_v25",
        "labels": ["person", "national id number", "tax identification number", "bank account number", "social security number"]
    }
}

# Mapeo de normalización para homogeneizar el CSV de salida
LABEL_NORMALIZE_MAP = {
    "national id number": "national_id_number",
    "tax identification number": "tax_id",
    "bank account number": "bank_account",
    "social security number": "social_security_number",
}

# Grupos de deduplicación intra-modelo (con etiquetas ya normalizadas)
DEDUP_GROUPS = [
    ["national_id_number", "government_id", "tax_id", "social_security_number"],
    ["bank_account", "account_number"],
]

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
    """
    if not entities:
        return []

    label_info = _build_label_to_group(dedup_groups)

    grouped = defaultdict(list)
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

        removed = set()
        for i, ent_i in enumerate(group_entities):
            if i in removed:
                continue
            for j in range(i + 1, len(group_entities)):
                if j in removed:
                    continue
                ent_j = group_entities[j]
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

    kept.sort(key=lambda e: (e["span_inicio"], e["span_fin"]))
    return kept


def _chunk_text_with_overlap(text, chunk_size_words=250, overlap_words=40):
    """
    Divide un texto en trozos (chunks) de palabras con solapamiento,
    calculando con precisión el offset en caracteres del inicio del chunk.
    """
    words = text.split()
    if not words:
        return
    if len(words) <= chunk_size_words:
        yield text, 0
        return

    step = max(1, chunk_size_words - overlap_words)
    
    # Calcular posiciones reales en caracteres de cada palabra
    word_indices = []
    current_idx = 0
    for w in words:
        idx = text.find(w, current_idx)
        if idx != -1:
            word_indices.append(idx)
            current_idx = idx + len(w)
        else:
            word_indices.append(current_idx)
            current_idx += len(w) + 1

    for i in range(0, len(words), step):
        chunk_words = words[i : i + chunk_size_words]
        chunk_str = " ".join(chunk_words)
        start_char = word_indices[i]
        yield chunk_str, start_char


def load_model(model_key, device):
    """Importa dinámicamente y carga el modelo correspondiente."""
    config = MODEL_REGISTRY[model_key]
    hf_name = config["hf_name"]
    library = config["library"]
    
    logger.info("Cargando modelo '%s' desde HuggingFace (%s)...", hf_name, library)
    
    if library == "gliner2":
        from gliner2 import GLiNER2
        model = GLiNER2.from_pretrained(hf_name)
    else:
        from gliner import GLiNER
        model = GLiNER.from_pretrained(hf_name)

    if device == "cuda":
        import torch
        if torch.cuda.is_available():
            model = model.to("cuda")
            logger.info("Modelo cargado y transferido a GPU (CUDA).")
        else:
            logger.warning("CUDA no disponible, usando CPU.")
    else:
        logger.info("Modelo cargado en CPU.")
        
    return model, library


def extract_from_text(model, library, text, labels, threshold, chunk_size, chunk_overlap):
    """
    Extrae y normaliza las entidades del texto, manejando fragmentación si es necesario.
    """
    if not text or not text.strip():
        return []

    entities = []

    # Estrategia nativa de GLiNER2 si está disponible
    if library == "gliner2" and hasattr(model, "extract_entities_long"):
        try:
            result = model.extract_entities_long(
                text,
                labels,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                include_spans=True,
                include_confidence=True,
            )
            raw_dict = {}
            if isinstance(result, dict) and "entities" in result:
                raw_dict = result["entities"]
            elif isinstance(result, dict):
                raw_dict = result

            for label, matches in raw_dict.items():
                if not isinstance(matches, list):
                    matches = [matches]
                for match in matches:
                    if isinstance(match, dict):
                        conf = match.get("confidence", match.get("score", 1.0))
                        if conf >= threshold:
                            norm_label = LABEL_NORMALIZE_MAP.get(label, label)
                            entities.append({
                                "etiqueta": norm_label,
                                "valor": match.get("text", match.get("entity", "")),
                                "span_inicio": match.get("start", 0),
                                "span_fin": match.get("end", 0),
                                "score": round(conf, 4),
                            })
            return entities
        except Exception as e:
            logger.warning("Fallo en extract_entities_long nativo: %s. Usando fallback...", e)

    # Fallback / Lógica manual por Chunks (necesaria para la librería gliner)
    # Estimación simple de tokens a palabras
    words_per_chunk = int(chunk_size / 1.3)
    words_overlap = int(chunk_overlap / 1.3)

    chunks = list(_chunk_text_with_overlap(text, words_per_chunk, words_overlap))
    seen_spans = set()

    for chunk_str, start_char_offset in chunks:
        try:
            if library == "gliner2":
                if hasattr(model, "extract_entities"):
                    res = model.extract_entities(chunk_str, labels)
                else:
                    res = model(chunk_str, labels)
            else:
                # Librería gliner original
                res = model.predict_entities(chunk_str, labels, threshold=threshold)
        except Exception as e:
            logger.warning("Error al procesar chunk: %s", e)
            continue

        # Normalizar salida según librería
        matches_list = []
        if library == "gliner2":
            if isinstance(res, dict):
                if "entities" in res:
                    res = res["entities"]
                for label, vals in res.items():
                    if label not in labels:
                        continue
                    if isinstance(vals, list):
                        for v in vals:
                            if isinstance(v, dict):
                                matches_list.append((
                                    label,
                                    v.get("text", v.get("entity", "")),
                                    v.get("score", 1.0),
                                    v.get("start", -1),
                                    v.get("end", -1)
                                ))
                            elif isinstance(v, str):
                                matches_list.append((label, v, 1.0, -1, -1))
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
        else:
            # gliner original devuelve una lista de dicts: [{"text":..., "label":..., "start":..., "end":..., "score":...}]
            if isinstance(res, list):
                for item in res:
                    if isinstance(item, dict):
                        lbl = item.get("label", "")
                        val = item.get("text", "")
                        score = item.get("score", 1.0)
                        st = item.get("start", -1)
                        en = item.get("end", -1)
                        if lbl in labels:
                            matches_list.append((lbl, val, score, st, en))

        # Re-mapear offsets de la ventana al texto original
        for lbl, val, score, st, en in matches_list:
            if not val or score < threshold:
                continue

            # Ajustar offsets
            if st != -1 and en != -1:
                global_st = start_char_offset + st
                global_en = start_char_offset + en
            else:
                global_st = text.find(val, start_char_offset)
                if global_st != -1:
                    global_en = global_st + len(val)
                else:
                    global_st, global_en = 0, len(val)

            norm_lbl = LABEL_NORMALIZE_MAP.get(lbl, lbl)
            key = (norm_lbl, val, global_st, global_en)
            if key not in seen_spans:
                seen_spans.add(key)
                entities.append({
                    "etiqueta": norm_lbl,
                    "valor": val,
                    "span_inicio": global_st,
                    "span_fin": global_en,
                    "score": round(score, 4),
                })

    return entities


def process_csv(model, library, model_key, args):
    """
    Procesa el CSV de entrada fila por fila, aplicando el modelo seleccionado.
    """
    logger.info("[%s] Leyendo CSV de entrada: %s", model_key, args.input)
    df = pd.read_csv(args.input, sep=args.separator, encoding="utf-8")
    logger.info("[%s] Registros a procesar: %d", model_key, len(df))

    if args.text_column not in df.columns:
        logger.error("La columna '%s' no existe en el CSV.", args.text_column)
        sys.exit(1)

    labels = MODEL_REGISTRY[model_key]["labels"]
    results = []
    total_entities_raw = 0
    total_entities_dedup = 0
    numero_archivo = 0
    id_anterior = None

    for _, row in tqdm(df.iterrows(), total=len(df), desc=f"Inferencia [{model_key}]"):
        current_id = row.get("id", "")
        if current_id != id_anterior:
            numero_archivo += 1
            id_anterior = current_id

        text = str(row[args.text_column]) if pd.notna(row[args.text_column]) else ""

        # Extracción
        raw_entities = extract_from_text(
            model,
            library,
            text,
            labels,
            args.threshold,
            args.chunk_size,
            args.chunk_overlap,
        )
        total_entities_raw += len(raw_entities)

        # Deduplicación
        clean_entities = deduplicate_entities(raw_entities, DEDUP_GROUPS)
        total_entities_dedup += len(clean_entities)

        # Estructurar resultados
        for entity in clean_entities:
            results.append({
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
            })

    logger.info(
        "[%s] Entidades: %d detectadas -> %d después de deduplicar.",
        model_key,
        total_entities_raw,
        total_entities_dedup,
    )

    output_df = pd.DataFrame(results)
    if output_df.empty:
        output_df = pd.DataFrame(columns=[
            "numero_archivo", "id", "nombre_archivo", "clasificacion",
            "texto_limpio", "etiqueta", "valor", "span_inicio", "span_fin", "score"
        ])
    return output_df


def save_outputs(output_df, model_key, args):
    """Guarda los archivos usando el formato dinámico: {confianza}_{chunk_size}_{chunk_overlap}_{modelo}.csv/json en output_dir."""
    prefix = MODEL_REGISTRY[model_key]["prefix"]
    
    output_dir = args.output_dir if args.output_dir else "."
    os.makedirs(output_dir, exist_ok=True)
        
    # Formatear el valor de confianza como entero (ej. 0.8 -> 80, 0.5 -> 50, 0.85 -> 85)
    conf_val = int(round(args.threshold * 100)) if args.threshold <= 1.0 else int(args.threshold)
    
    # Nombre automático: {confianza}_{chunk_size}_{chunk_overlap}_{prefix}.csv / .json
    if hasattr(args, "output_csv") and args.output_csv and args.output_csv != "output.csv":
        csv_filename = f"{prefix}_{args.output_csv}"
    else:
        csv_filename = f"{conf_val}_{args.chunk_size}_{args.chunk_overlap}_{prefix}.csv"
        
    if hasattr(args, "output_json") and args.output_json and args.output_json != "output.json":
        json_filename = f"{prefix}_{args.output_json}"
    else:
        json_filename = f"{conf_val}_{args.chunk_size}_{args.chunk_overlap}_{prefix}.json"
    
    csv_path = os.path.join(output_dir, csv_filename)
    json_path = os.path.join(output_dir, json_filename)

    # CSV
    output_df.to_csv(csv_path, sep=";", index=False, encoding="utf-8")
    logger.info("[%s] CSV guardado en: %s (%d filas)", model_key, csv_path, len(output_df))

    # JSON
    records = output_df.to_dict(orient="records")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info("[%s] JSON guardado en: %s", model_key, json_path)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Script de extracción multi-modelo PII usando GLiNER y GLiNER2.",
    )
    parser.add_argument(
        "--input", required=True, help="Ruta al CSV de entrada."
    )
    parser.add_argument(
        "--output-dir", default=".", help="Directorio donde se generarán los resultados (default: .)."
    )
    parser.add_argument(
        "--output-csv", default=None, help="Nombre base personalizado para el CSV (opcional, por defecto es automático)."
    )
    parser.add_argument(
        "--output-json", default=None, help="Nombre base personalizado para el JSON (opcional, por defecto es automático)."
    )
    parser.add_argument(
        "--model",
        nargs="+",
        default=["gliner2"],
        help="Modelos a ejecutar: gliner2, pii_v1, large_v25 o 'all' para todos (default: gliner2)."
    )
    parser.add_argument(
        "--text-column", default="texto_limpio", help="Columna del CSV con el texto."
    )
    parser.add_argument(
        "--threshold", type=float, default=0.5, help="Umbral de confianza (default: 0.5)."
    )
    parser.add_argument(
        "--separator", default=";", help="Separador del CSV de entrada."
    )
    parser.add_argument(
        "--device", default="cpu", choices=["cpu", "cuda"], help="Dispositivo (default: cpu)."
    )
    parser.add_argument(
        "--chunk-size", type=int, default=384, help="Tamaño de ventana en tokens."
    )
    parser.add_argument(
        "--chunk-overlap", type=int, default=64, help="Solapamiento de ventana."
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Resolver lista de modelos a ejecutar
    selected_models = args.model
    if "all" in selected_models:
        models_to_run = list(MODEL_REGISTRY.keys())
    else:
        models_to_run = [m for m in selected_models if m in MODEL_REGISTRY]
        if not models_to_run:
            logger.error("Ninguno de los modelos especificados (%s) es válido.", selected_models)
            sys.exit(1)

    logger.info("=" * 60)
    logger.info("EXTRACCIÓN MULTI-MODELO PII")
    logger.info("Modelos a ejecutar: %s", models_to_run)
    logger.info("Dispositivo: %s | Confianza: %.2f", args.device, args.threshold)
    logger.info("=" * 60)

    global_start_time = time.time()
    summaries = []

    for model_key in models_to_run:
        logger.info("-" * 60)
        logger.info("PROCESANDO MODELO: %s", model_key)
        logger.info("-" * 60)
        
        try:
            start_load = time.time()
            model, library = load_model(model_key, args.device)
            load_time = time.time() - start_load
            
            start_proc = time.time()
            output_df = process_csv(model, library, model_key, args)
            proc_time = time.time() - start_proc
            
            save_outputs(output_df, model_key, args)
            
            summaries.append({
                "modelo": model_key,
                "tiempo_carga": load_time,
                "tiempo_procesamiento": proc_time,
                "entidades": len(output_df),
                "estado": "Éxito"
            })
            
            # Liberar GPU/Memoria
            del model
            import gc
            gc.collect()
            if args.device == "cuda":
                import torch
                torch.cuda.empty_cache()
                
        except Exception as e:
            logger.error("Error al procesar modelo '%s': %s", model_key, e, exc_info=True)
            summaries.append({
                "modelo": model_key,
                "tiempo_carga": 0.0,
                "tiempo_procesamiento": 0.0,
                "entidades": 0,
                "estado": f"Error: {e}"
            })

    total_time = time.time() - global_start_time
    logger.info("=" * 60)
    logger.info("RESUMEN GLOBAL DE EJECUCIÓN")
    logger.info("=" * 60)
    logger.info("Tiempo Total: %.1f segundos", total_time)
    for s in summaries:
        logger.info(
            "Modelo: %-12s | Estado: %-10s | Carga: %4.1fs | Proc: %5.1fs | Entidades: %d",
            s["modelo"], s["estado"], s["tiempo_carga"], s["tiempo_procesamiento"], s["entidades"]
        )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
