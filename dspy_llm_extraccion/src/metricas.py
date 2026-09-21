"""
metricas.py - Métricas de evaluación para la extracción de embargos judiciales.
"""

from typing import Dict, Any, List, Tuple, Union, Optional
import dspy
from src.normalizacion import (
    normalizar_dni,
    normalizar_cuit,
    normalizar_monto,
    normalizar_nombre,
    similitud_nombre,
    fuzzy_match_nombre,
    normalizar_cuenta,
)


def _parsear_lista_pipe(texto: Optional[str]) -> List[str]:
    """Divide un texto separado por '|' y limpia cada elemento."""
    if not texto:
        return []
    partes = [p.strip() for p in str(texto).split("|")]
    return partes


def evaluar_personas(
    gold_nombres: str,
    gold_dnis: str,
    gold_cuits: str,
    pred_nombres: str,
    pred_dnis: str,
    pred_cuits: str,
) -> Dict[str, float]:
    """
    Evalúa las personas embargadas extraídas frente a las de referencia.
    Soporta múltiples personas separadas por '|'.
    
    Retorna dict con:
      - score_personas: [0.0, 1.0]
      - score_nombre: [0.0, 1.0]
      - score_dni: [0.0, 1.0]
      - score_cuit: [0.0, 1.0]
    """
    g_noms = _parsear_lista_pipe(gold_nombres)
    g_dnis = _parsear_lista_pipe(gold_dnis)
    g_cuits = _parsear_lista_pipe(gold_cuits)

    p_noms = _parsear_lista_pipe(pred_nombres)
    p_dnis = _parsear_lista_pipe(pred_dnis)
    p_cuits = _parsear_lista_pipe(pred_cuits)

    # Si ambos están completamente vacíos
    if not g_noms and not p_noms:
        return {
            "score_personas": 1.0,
            "score_nombre": 1.0,
            "score_dni": 1.0,
            "score_cuit": 1.0,
        }
    
    # Si uno tiene personas y el otro ninguna
    if not g_noms or not p_noms:
        return {
            "score_personas": 0.0,
            "score_nombre": 0.0,
            "score_dni": 0.0,
            "score_cuit": 0.0,
        }

    # Armar tuplas de personas
    max_g = max(len(g_noms), len(g_dnis), len(g_cuits))
    personas_gold = []
    for i in range(max_g):
        nom = g_noms[i] if i < len(g_noms) else ""
        dni = g_dnis[i] if i < len(g_dnis) else ""
        cuit = g_cuits[i] if i < len(g_cuits) else ""
        personas_gold.append({"nombre": nom, "dni": dni, "cuit": cuit})

    max_p = max(len(p_noms), len(p_dnis), len(p_cuits))
    personas_pred = []
    for i in range(max_p):
        nom = p_noms[i] if i < len(p_noms) else ""
        dni = p_dnis[i] if i < len(p_dnis) else ""
        cuit = p_cuits[i] if i < len(p_cuits) else ""
        personas_pred.append({"nombre": nom, "dni": dni, "cuit": cuit})

    # Emparejar predicciones con gold mediante matching voraz (bipartite greedy)
    matches: List[Tuple[int, int, float, float, float]] = []  # (g_idx, p_idx, s_nom, s_dni, s_cuit)
    usados_pred = set()

    for g_idx, g in enumerate(personas_gold):
        mejor_p_idx = -1
        mejor_score_combinado = -1.0
        mejores_subscores = (0.0, 0.0, 0.0)

        for p_idx, p in enumerate(personas_pred):
            if p_idx in usados_pred:
                continue

            # Evaluar nombre (fuzzy)
            s_nom = similitud_nombre(g["nombre"], p["nombre"])

            # Evaluar DNI
            d_g = normalizar_dni(g["dni"])
            d_p = normalizar_dni(p["dni"])
            if not d_g and not d_p:
                s_dni = 1.0
            elif d_g and d_p and d_g == d_p:
                s_dni = 1.0
            else:
                s_dni = 0.0

            # Evaluar CUIT
            c_g = normalizar_cuit(g["cuit"])
            c_p = normalizar_cuit(p["cuit"])
            if not c_g and not c_p:
                s_cuit = 1.0
            elif c_g and c_p and c_g == c_p:
                s_cuit = 1.0
            else:
                s_cuit = 0.0

            # Score combinado de la persona: nombre (50%), DNI (25%), CUIT (25%)
            score_comb = (0.50 * s_nom) + (0.25 * s_dni) + (0.25 * s_cuit)

            if score_comb > mejor_score_combinado:
                mejor_score_combinado = score_comb
                mejor_p_idx = p_idx
                mejores_subscores = (s_nom, s_dni, s_cuit)

        if mejor_p_idx != -1 and mejor_score_combinado > 0.2:
            usados_pred.add(mejor_p_idx)
            matches.append((g_idx, mejor_p_idx, mejores_subscores[0], mejores_subscores[1], mejores_subscores[2]))

    # Calcular precisión y recall
    num_gold = len(personas_gold)
    num_pred = len(personas_pred)

    if not matches:
        return {
            "score_personas": 0.0,
            "score_nombre": 0.0,
            "score_dni": 0.0,
            "score_cuit": 0.0,
        }

    sum_nom = sum(m[2] for m in matches)
    sum_dni = sum(m[3] for m in matches)
    sum_cuit = sum(m[4] for m in matches)

    # Penalizar tanto falsos positivos como falsos negativos (F1 normalizado)
    denominador = max(num_gold, num_pred)

    final_nom = sum_nom / denominador
    final_dni = sum_dni / denominador
    final_cuit = sum_cuit / denominador
    score_personas = (0.50 * final_nom) + (0.25 * final_dni) + (0.25 * final_cuit)

    return {
        "score_personas": min(1.0, max(0.0, score_personas)),
        "score_nombre": min(1.0, max(0.0, final_nom)),
        "score_dni": min(1.0, max(0.0, final_dni)),
        "score_cuit": min(1.0, max(0.0, final_cuit)),
    }


def evaluar_monto(gold_monto: Any, pred_monto: Any) -> float:
    """
    Evalúa si el monto_total extraído coincide con el de referencia.
    Compara valores normalizados como floats.
    """
    m_gold = normalizar_monto(gold_monto)
    m_pred = normalizar_monto(pred_monto)

    # Ambos numéricos
    if m_gold is not None and m_pred is not None:
        # Tolerancia para diferencias de redondeo (< 1 peso o < 0.1%)
        if abs(m_gold - m_pred) < 1.0 or (m_gold > 0 and abs(m_gold - m_pred) / m_gold < 0.001):
            return 1.0
        return 0.0

    # Ambos no numéricos o vacíos
    str_g = str(gold_monto or "").strip().lower()
    str_p = str(pred_monto or "").strip().lower()

    if not str_g and not str_p:
        return 1.0

    if str_g == str_p:
        return 1.0

    return 0.0


def evaluar_cuenta(gold_cuenta: Any, pred_cuenta: Any) -> float:
    """
    Evalúa si la cuenta judicial extraída coincide con la de referencia.
    """
    c_gold = normalizar_cuenta(gold_cuenta)
    c_pred = normalizar_cuenta(pred_cuenta)

    if not c_gold and not c_pred:
        return 1.0

    if not c_gold or not c_pred:
        return 0.0

    if c_gold == c_pred:
        return 1.0

    # Coincidencia parcial (ej: CBU contiene número de cuenta de autos o viceversa)
    if len(c_gold) >= 6 and len(c_pred) >= 6:
        if c_gold in c_pred or c_pred in c_gold:
            return 0.70

    return 0.0


def desglose_metricas(example: dspy.Example, pred: dspy.Prediction) -> Dict[str, float]:
    """
    Calcula el desglose completo de métricas entre un ejemplo de referencia y una predicción.
    """
    # 1. Personas (40%)
    res_personas = evaluar_personas(
        gold_nombres=getattr(example, "nombre_embargado", ""),
        gold_dnis=getattr(example, "dni", ""),
        gold_cuits=getattr(example, "cuit_cuil", ""),
        pred_nombres=getattr(pred, "nombre_embargado", ""),
        pred_dnis=getattr(pred, "dni", ""),
        pred_cuits=getattr(pred, "cuit_cuil", ""),
    )
    score_personas = res_personas["score_personas"]

    # 2. Monto total (35%)
    score_monto = evaluar_monto(
        gold_monto=getattr(example, "monto_total", ""),
        pred_monto=getattr(pred, "monto_total", ""),
    )

    # 3. Cuenta judicial (25%)
    score_cuenta = evaluar_cuenta(
        gold_cuenta=getattr(example, "cuenta", ""),
        pred_cuenta=getattr(pred, "cuenta", ""),
    )

    # Score ponderado global
    score_global = (0.40 * score_personas) + (0.35 * score_monto) + (0.25 * score_cuenta)

    return {
        "score_global": round(score_global, 4),
        "score_personas": round(score_personas, 4),
        "score_nombre": round(res_personas["score_nombre"], 4),
        "score_dni": round(res_personas["score_dni"], 4),
        "score_cuit": round(res_personas["score_cuit"], 4),
        "score_monto": round(score_monto, 4),
        "score_cuenta": round(score_cuenta, 4),
    }


def metrica_embargo(example: dspy.Example, pred: dspy.Prediction, trace=None) -> Union[float, bool]:
    """
    Métrica principal compatible con DSPy Evaluate y optimizadores (BootstrapFewShot, MIPROv2).
    
    - En evaluación (trace is None): retorna float [0.0, 1.0].
    - En optimización (trace is not None): retorna bool (score_global >= 0.70) para filtrar
      demostraciones de alta calidad en pocos tiros.
    """
    desglose = desglose_metricas(example, pred)
    score = desglose["score_global"]

    if trace is not None:
        # Modo optimización de DSPy: retorno booleano
        return score >= 0.70

    return score
