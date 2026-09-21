"""
evaluar.py - Evaluación independiente de extractores DSPy (baseline o compilados) sobre test o validación.

Uso:
    python evaluar.py --split test
    python evaluar.py --prog programas/embargo_optimizado.json --split test
    python evaluar.py --prog programas/embargo_optimizado.json --split test --output-csv output/eval_test.csv
"""

import os
import sys
import csv
import argparse
from typing import List, Dict, Any
import dspy

from src.utils import configurar_lm, setup_logging, cargar_config
from src.dataset import cargar_bd_supervisada, crear_ejemplos_dspy, split_dataset
from src.extractor import ExtraerEmbargo
from src.metricas import desglose_metricas


def main():
    parser = argparse.ArgumentParser(description="Evaluar modelo DSPy en dataset de prueba o validación.")
    parser.add_argument("--config", default="config/embargo.yaml", help="Ruta al archivo YAML de configuración")
    parser.add_argument("--prog", default=None, help="Ruta al programa DSPy compilado (si se omite, evalúa Zero-Shot)")
    parser.add_argument("--split", choices=["test", "val", "all", "train"], default="test", help="Conjunto a evaluar")
    parser.add_argument("--campo", choices=["contexto", "texto_completo"], default=None, help="Campo de texto a usar")
    parser.add_argument("--output-csv", default=None, help="Ruta opcional para exportar los resultados detallados a CSV")
    args = parser.parse_args()

    logger = setup_logging()
    cfg = cargar_config(args.config)

    campo_texto = args.campo or cfg.get("datos", {}).get("campo_entrenamiento", "contexto")
    split_cfg = cfg.get("datos", {}).get("split", {})

    logger.info("=== INICIANDO EVALUACIÓN DSPY ===")
    logger.info(f"Conjunto seleccionado: {args.split.upper()} | Campo: {campo_texto}")

    # 1. Configurar LLM
    llm_cfg = cfg.get("llm", {})
    configurar_lm(
        api_base=llm_cfg.get("api_base", "http://localhost:1234/v1"),
        model=llm_cfg.get("model", "openai/local-model"),
        temperature=llm_cfg.get("temperature", 0.0),
        max_tokens=llm_cfg.get("max_tokens", 1500),
        api_key=llm_cfg.get("api_key", "local")
    )

    # 2. Cargar datos
    bd_path = cfg.get("datos", {}).get("bd_supervisada", "bd_supervisada_embargos_actualizada.csv")
    frag_path = cfg.get("datos", {}).get("frag_con_texto", "frag_con_texto.csv")

    documentos = cargar_bd_supervisada(bd_path, ruta_frag_con_texto=frag_path)
    ejemplos = crear_ejemplos_dspy(documentos, campo_documento=campo_texto)

    trainset, valset, testset = split_dataset(
        ejemplos,
        train_ratio=split_cfg.get("train", 0.60),
        val_ratio=split_cfg.get("val", 0.20),
        test_ratio=split_cfg.get("test", 0.20),
        seed=split_cfg.get("seed", 42),
        priorizar_multiples_en_train=split_cfg.get("priorizar_multiples", True)
    )

    if args.split == "test":
        target_set = testset
    elif args.split == "val":
        target_set = valset
    elif args.split == "train":
        target_set = trainset
    else:
        target_set = ejemplos

    logger.info(f"Evaluando sobre {len(target_set)} ejemplos...")

    # 3. Cargar módulo
    cot = cfg.get("extraccion", {}).get("cot", False)
    max_chars = cfg.get("extraccion", {}).get("max_chars", 12000)
    extractor = ExtraerEmbargo(cot=cot, max_chars=max_chars)

    if args.prog:
        logger.info(f"Cargando programa compilado desde: {args.prog}")
        extractor.cargar(args.prog)
    else:
        logger.info("Sin programa especificado. Evaluando en modo Zero-Shot.")

    # 4. Evaluación y recolección de métricas
    acumuladores = {
        "score_global": 0.0,
        "score_personas": 0.0,
        "score_nombre": 0.0,
        "score_dni": 0.0,
        "score_cuit": 0.0,
        "score_monto": 0.0,
        "score_cuenta": 0.0,
    }

    filas_detalle = []

    for i, ex in enumerate(target_set, 1):
        doc_id = getattr(ex, "doc_id", f"doc_{i}")
        logger.info(f"Procesando [{i}/{len(target_set)}] - ID: {doc_id}...")

        try:
            pred = extractor(documento=ex.documento)
            scores = desglose_metricas(ex, pred)
        except Exception as e:
            logger.error(f"Error en predicción para ID {doc_id}: {e}")
            pred = dspy.Prediction(
                nombre_embargado="",
                dni="",
                cuit_cuil="",
                monto_total="",
                monto_contexto="",
                cuenta=""
            )
            scores = {k: 0.0 for k in acumuladores}

        for k in acumuladores:
            acumuladores[k] += scores[k]

        filas_detalle.append({
            "id": doc_id,
            "numero_archivo": getattr(ex, "numero_archivo", ""),
            "nombre": getattr(ex, "nombre", ""),
            "gold_nombre_embargado": getattr(ex, "nombre_embargado", ""),
            "pred_nombre_embargado": getattr(pred, "nombre_embargado", ""),
            "score_nombre": scores["score_nombre"],
            "gold_dni": getattr(ex, "dni", ""),
            "pred_dni": getattr(pred, "dni", ""),
            "score_dni": scores["score_dni"],
            "gold_cuit_cuil": getattr(ex, "cuit_cuil", ""),
            "pred_cuit_cuil": getattr(pred, "cuit_cuil", ""),
            "score_cuit": scores["score_cuit"],
            "gold_monto_total": getattr(ex, "monto_total", ""),
            "pred_monto_total": getattr(pred, "monto_total", ""),
            "score_monto": scores["score_monto"],
            "pred_monto_contexto": getattr(pred, "monto_contexto", ""),
            "gold_cuenta": getattr(ex, "cuenta", ""),
            "pred_cuenta": getattr(pred, "cuenta", ""),
            "score_cuenta": scores["score_cuenta"],
            "score_global": scores["score_global"],
        })

    n = max(1, len(target_set))
    promedios = {k: round(v / n, 4) for k, v in acumuladores.items()}

    print("\n" + "=" * 65)
    print(f" REPORTE FINAL DE EVALUACIÓN [{args.split.upper()}] - {len(target_set)} DOCS")
    print("=" * 65)
    print(f"  Score Global Ponderado:    {promedios['score_global'] * 100:.1f}%")
    print(f"  ├── Personas (40% peso):   {promedios['score_personas'] * 100:.1f}%")
    print(f"  │   ├── Nombres (Fuzzy):   {promedios['score_nombre'] * 100:.1f}%")
    print(f"  │   ├── DNI:               {promedios['score_dni'] * 100:.1f}%")
    print(f"  │   └── CUIT/CUIL:         {promedios['score_cuit'] * 100:.1f}%")
    print(f"  ├── Monto Total (35% peso):{promedios['score_monto'] * 100:.1f}%")
    print(f"  └── Cuenta Judicial (25%): {promedios['score_cuenta'] * 100:.1f}%")
    print("=" * 65 + "\n")

    if args.output_csv:
        os.makedirs(os.path.dirname(os.path.abspath(args.output_csv)), exist_ok=True)
        with open(args.output_csv, "w", encoding="utf-8-sig", newline="") as f:
            if filas_detalle:
                writer = csv.DictWriter(f, fieldnames=list(filas_detalle[0].keys()), delimiter=";")
                writer.writeheader()
                for row in filas_detalle:
                    writer.writerow(row)
        logger.info(f"Detalle de evaluación guardado en CSV: {args.output_csv}")


if __name__ == "__main__":
    main()
