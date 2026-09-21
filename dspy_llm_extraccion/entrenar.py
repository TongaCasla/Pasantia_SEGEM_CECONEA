"""
entrenar.py - Entrenamiento y optimización de prompts/demostraciones DSPy para extracción judicial.

Uso:
    python entrenar.py --eval-only
    python entrenar.py --optimizer BootstrapFewShot --demos 4
    python entrenar.py --campo texto_completo
"""

import os
import sys
import argparse
from typing import List, Dict, Any
import dspy

from src.utils import configurar_lm, setup_logging, cargar_config
from src.dataset import cargar_bd_supervisada, crear_ejemplos_dspy, split_dataset
from src.extractor import ExtraerEmbargo
from src.metricas import metrica_embargo, desglose_metricas


def evaluar_conjunto(
    modulo: dspy.Module,
    ejemplos: List[dspy.Example],
    nombre_conjunto: str = "validación"
) -> Dict[str, float]:
    """
    Evalúa un módulo DSPy sobre una lista de ejemplos y calcula promedios detallados.
    """
    logger = setup_logging()
    logger.info(f"Iniciando evaluación sobre conjunto de {nombre_conjunto} ({len(ejemplos)} ejemplos)...")

    acumuladores = {
        "score_global": 0.0,
        "score_personas": 0.0,
        "score_nombre": 0.0,
        "score_dni": 0.0,
        "score_cuit": 0.0,
        "score_monto": 0.0,
        "score_cuenta": 0.0,
    }

    detalles_ejemplos = []

    for i, ex in enumerate(ejemplos, 1):
        try:
            pred = modulo(documento=ex.documento)
            scores = desglose_metricas(ex, pred)
        except Exception as e:
            logger.error(f"Error al evaluar ejemplo {i} (ID: {getattr(ex, 'doc_id', 'N/A')}): {e}")
            scores = {k: 0.0 for k in acumuladores}

        for k in acumuladores:
            acumuladores[k] += scores[k]

        detalles_ejemplos.append({
            "id": getattr(ex, "doc_id", "N/A"),
            "scores": scores
        })

    n = max(1, len(ejemplos))
    promedios = {k: round(v / n, 4) for k, v in acumuladores.items()}

    print("\n" + "=" * 65)
    print(f" RESULTADOS DE EVALUACIÓN - CONJUNTO: {nombre_conjunto.upper()}")
    print("=" * 65)
    print(f"  Score Global Ponderado:    {promedios['score_global'] * 100:.1f}%")
    print(f"  ├── Personas (40% peso):   {promedios['score_personas'] * 100:.1f}%")
    print(f"  │   ├── Nombres (Fuzzy):   {promedios['score_nombre'] * 100:.1f}%")
    print(f"  │   ├── DNI:               {promedios['score_dni'] * 100:.1f}%")
    print(f"  │   └── CUIT/CUIL:         {promedios['score_cuit'] * 100:.1f}%")
    print(f"  ├── Monto Total (35% peso):{promedios['score_monto'] * 100:.1f}%")
    print(f"  └── Cuenta Judicial (25%): {promedios['score_cuenta'] * 100:.1f}%")
    print("=" * 65 + "\n")

    return promedios


def main():
    parser = argparse.ArgumentParser(description="Entrenar y optimizar extractor DSPy de embargos judiciales.")
    parser.add_argument("--config", default="config/embargo.yaml", help="Ruta al archivo YAML de configuración")
    parser.add_argument("--optimizer", choices=["BootstrapFewShot", "MIPROv2"], default=None, help="Optimizador DSPy")
    parser.add_argument("--campo", choices=["contexto", "texto_completo"], default=None, help="Campo de texto a utilizar")
    parser.add_argument("--demos", type=int, default=None, help="Cantidad de demostraciones pocos-tiros")
    parser.add_argument("--eval-only", action="store_true", help="Solo evaluar baseline sin optimizar")
    parser.add_argument("--train-ratio", type=float, default=None, help="Proporción para train (0.0 a 1.0)")
    parser.add_argument("--val-ratio", type=float, default=None, help="Proporción para val (0.0 a 1.0)")
    parser.add_argument("--seed", type=int, default=None, help="Semilla para reproducibilidad")
    parser.add_argument("--output-prog", default=None, help="Ruta de guardado del programa optimizado")
    args = parser.parse_args()

    # 1. Configuración y logging
    logger = setup_logging()
    cfg = cargar_config(args.config)

    campo_texto = args.campo or cfg.get("datos", {}).get("campo_entrenamiento", "contexto")
    metodo_opt = args.optimizer or cfg.get("optimizador", {}).get("metodo", "BootstrapFewShot")
    num_demos = args.demos or cfg.get("optimizador", {}).get("max_bootstrapped_demos", 4)
    ruta_output_prog = args.output_prog or cfg.get("rutas", {}).get("programa_compilado", "programas/embargo_optimizado.json")

    split_cfg = cfg.get("datos", {}).get("split", {})
    t_ratio = args.train_ratio if args.train_ratio is not None else split_cfg.get("train", 0.60)
    v_ratio = args.val_ratio if args.val_ratio is not None else split_cfg.get("val", 0.20)
    semilla = args.seed if args.seed is not None else split_cfg.get("seed", 42)
    priorizar_multiples = split_cfg.get("priorizar_multiples", True)

    logger.info("=== INICIANDO PIPELINE DE ENTRENAMIENTO / OPTIMIZACIÓN DSPY ===")
    logger.info(f"Campo de entrenamiento: {campo_texto}")
    logger.info(f"Optimizador: {metodo_opt} (demos: {num_demos})")

    # 2. Configurar LLM
    llm_cfg = cfg.get("llm", {})
    configurar_lm(
        api_base=llm_cfg.get("api_base", "http://localhost:1234/v1"),
        model=llm_cfg.get("model", "openai/local-model"),
        temperature=llm_cfg.get("temperature", 0.0),
        max_tokens=llm_cfg.get("max_tokens", 1500),
        api_key=llm_cfg.get("api_key", "local")
    )

    # 3. Cargar datos supervisados y preparar dataset
    bd_path = cfg.get("datos", {}).get("bd_supervisada", "bd_supervisada_embargos_actualizada.csv")
    frag_path = cfg.get("datos", {}).get("frag_con_texto", "frag_con_texto.csv")

    documentos = cargar_bd_supervisada(bd_path, ruta_frag_con_texto=frag_path)
    ejemplos = crear_ejemplos_dspy(documentos, campo_documento=campo_texto)

    trainset, valset, testset = split_dataset(
        ejemplos,
        train_ratio=t_ratio,
        val_ratio=v_ratio,
        test_ratio=round(1.0 - t_ratio - v_ratio, 2),
        seed=semilla,
        priorizar_multiples_en_train=priorizar_multiples
    )

    # 4. Crear módulo base (Zero-Shot)
    cot = cfg.get("extraccion", {}).get("cot", False)
    max_chars = cfg.get("extraccion", {}).get("max_chars", 12000)
    extractor_base = ExtraerEmbargo(cot=cot, max_chars=max_chars)

    # 5. Evaluación Baseline (Zero-Shot)
    logger.info("Evaluando modelo base (Zero-Shot)...")
    res_base = evaluar_conjunto(extractor_base, valset, nombre_conjunto="Validación (Baseline Zero-Shot)")

    if args.eval_only:
        logger.info("Modo --eval-only activo. Finalizando sin compilar.")
        return

    # 6. Optimización DSPy
    logger.info(f"Compilando programa con {metodo_opt}...")

    if metodo_opt == "BootstrapFewShot":
        optimizador = dspy.BootstrapFewShot(
            metric=metrica_embargo,
            max_bootstrapped_demos=num_demos,
            max_labeled_demos=num_demos,
            max_rounds=cfg.get("optimizador", {}).get("max_rounds", 1)
        )
        programa_optimizado = optimizador.compile(
            student=extractor_base,
            trainset=trainset
        )
    elif metodo_opt == "MIPROv2":
        optimizador = dspy.MIPROv2(
            metric=metrica_embargo,
            auto="light",
            num_candidates=7,
        )
        programa_optimizado = optimizador.compile(
            student=extractor_base,
            trainset=trainset,
            valset=valset,
            max_bootstrapped_demos=num_demos,
            max_labeled_demos=num_demos,
        )
    else:
        logger.error(f"Optimizador no reconocido: {metodo_opt}")
        sys.exit(1)

    # 7. Evaluación del programa optimizado
    logger.info("Evaluando programa optimizado...")
    res_opt = evaluar_conjunto(programa_optimizado, valset, nombre_conjunto="Validación (Optimizado Few-Shot)")

    # Comparativa
    delta = (res_opt["score_global"] - res_base["score_global"]) * 100
    print("\n" + "#" * 65)
    print(f" COMPARATIVA FINAL (VALIDACIÓN): Baseline: {res_base['score_global']*100:.1f}% -> Optimizado: {res_opt['score_global']*100:.1f}% (Delta: {delta:+.1f}%)")
    print("#" * 65 + "\n")

    # 8. Guardar programa compilado
    logger.info(f"Guardando programa optimizado en: {ruta_output_prog}")
    os.makedirs(os.path.dirname(os.path.abspath(ruta_output_prog)), exist_ok=True)
    programa_optimizado.save(ruta_output_prog)
    logger.info("¡Optimización completada con éxito!")


if __name__ == "__main__":
    main()
