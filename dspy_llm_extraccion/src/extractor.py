"""
extractor.py - Módulo DSPy para la extracción de datos de embargos judiciales.
"""

import os
import logging
from typing import Optional, Dict, Any
import dspy
from src.modelos import ExtraccionEmbargo

logger = logging.getLogger("dspy_embargos")


class ExtraerEmbargo(dspy.Module):
    """
    Módulo DSPy para la extracción estructurada de datos de embargos judiciales.
    Encapsula el Predictor (Predict o ChainOfThought), truncado de texto y limpieza de salidas.
    """

    def __init__(self, cot: bool = False, max_chars: int = 12000):
        super().__init__()
        self.cot = cot
        self.max_chars = max_chars
        if cot:
            self.extractor = dspy.ChainOfThought(ExtraccionEmbargo)
        else:
            self.extractor = dspy.Predict(ExtraccionEmbargo)

    def forward(self, documento: str) -> dspy.Prediction:
        """
        Ejecuta la extracción sobre el documento judicial.
        """
        doc_texto = str(documento or "").strip()
        if len(doc_texto) > self.max_chars:
            doc_texto = doc_texto[:self.max_chars]

        # Inferencia DSPy
        pred = self.extractor(documento=doc_texto)

        # Limpieza de valores nulos o placeholders del LLM
        def limpiar(val: Any) -> str:
            if val is None:
                return ""
            s = str(val).strip()
            if s.lower() in ("n/a", "no encontrado", "no disponible", "none", "null", "no aplica", "s/d", "no indica"):
                return ""
            return s

        # Retornar objeto Prediction limpio
        return dspy.Prediction(
            nombre_embargado=limpiar(getattr(pred, "nombre_embargado", "")),
            dni=limpiar(getattr(pred, "dni", "")),
            cuit_cuil=limpiar(getattr(pred, "cuit_cuil", "")),
            monto_total=limpiar(getattr(pred, "monto_total", "")),
            monto_contexto=limpiar(getattr(pred, "monto_contexto", "")),
            cuenta=limpiar(getattr(pred, "cuenta", "")),
            rationale=getattr(pred, "rationale", "") if self.cot else "",
        )

    def extraer_dict(self, documento: str, max_reintentos: int = 2) -> Dict[str, str]:
        """
        Ejecuta forward con reintentos para lidiar con desconexiones transitorias de LM Studio.
        Retorna un diccionario plano con los campos extraídos.
        """
        for intento in range(max_reintentos + 1):
            try:
                pred = self.forward(documento)
                return {
                    "nombre_embargado": pred.nombre_embargado,
                    "dni": pred.dni,
                    "cuit_cuil": pred.cuit_cuil,
                    "monto_total": pred.monto_total,
                    "monto_contexto": pred.monto_contexto,
                    "cuenta": pred.cuenta,
                }
            except Exception as e:
                if intento < max_reintentos:
                    logger.warning(f"Error en extracción (intento {intento + 1}/{max_reintentos + 1}): {e}. Reintentando...")
                else:
                    logger.error(f"Fallo definitivo en extracción tras {max_reintentos + 1} intentos: {e}")
                    return {
                        "nombre_embargado": "",
                        "dni": "",
                        "cuit_cuil": "",
                        "monto_total": "",
                        "monto_contexto": "",
                        "cuenta": "",
                    }

    def guardar(self, ruta_archivo: str):
        """Guarda el programa DSPy optimizado a disco."""
        os.makedirs(os.path.dirname(os.path.abspath(ruta_archivo)), exist_ok=True)
        self.save(ruta_archivo)
        logger.info(f"Programa DSPy guardado en: {ruta_archivo}")

    def cargar(self, ruta_archivo: str):
        """Carga los parámetros y demostraciones de un programa DSPy optimizado."""
        if not os.path.exists(ruta_archivo):
            raise FileNotFoundError(f"Archivo de programa DSPy no encontrado: {ruta_archivo}")
        self.load(ruta_archivo)
        logger.info(f"Programa DSPy cargado desde: {ruta_archivo}")
