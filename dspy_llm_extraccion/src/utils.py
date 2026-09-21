"""
utils.py - Funciones auxiliares de LLM, configuración, logging, checkpoints y post-procesamiento.
"""

import os
import sys
import csv
import json
import logging
from typing import Dict, List, Any, Optional
import yaml
import dspy

# Silenciar logs ruidosos de litellm
os.environ["LITELLM_LOG"] = "ERROR"
try:
    import litellm
    litellm.suppress_debug_info = True
except ImportError:
    pass


class LocalLM(dspy.LM):
    """
    Subclase de dspy.LM para servidores locales (LM Studio / llama.cpp).
    Remueve 'response_format' de supported_params para evitar error HTTP 400
    cuando LM Studio rechaza formatos json no schema.
    """
    @property
    def supported_params(self) -> set[str]:
        return super().supported_params - {"response_format"}


def configurar_lm(
    api_base: str = "http://localhost:1234/v1",
    model: str = "openai/local-model",
    temperature: float = 0.0,
    max_tokens: int = 1500,
    api_key: str = "local"
) -> dspy.LM:
    """
    Inicializa y configura el modelo de lenguaje en DSPy.
    """
    lm = LocalLM(
        model=model,
        api_base=api_base,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    dspy.configure(lm=lm)
    return lm


def setup_logging(nivel: str = "INFO") -> logging.Logger:
    """Configura el logging estándar para la aplicación."""
    numeric_level = getattr(logging, nivel.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    return logging.getLogger("dspy_embargos")


def cargar_config(ruta_config: str) -> dict:
    """Carga y valida un archivo de configuración YAML."""
    if not os.path.exists(ruta_config):
        raise FileNotFoundError(f"Archivo de configuración no encontrado: {ruta_config}")

    with open(ruta_config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config or {}


# ---------------------------------------------------------------------------
# Checkpoint: guardar/cargar progreso para ejecuciones largas
# ---------------------------------------------------------------------------

def ruta_checkpoint(ruta_output: str) -> str:
    """Genera la ruta del archivo de checkpoint basada en el output."""
    base = os.path.splitext(ruta_output)[0]
    return base + "_checkpoint.json"


def cargar_checkpoint(ruta: str) -> Dict[str, Any]:
    """Carga el checkpoint si existe. Retorna dict {id: {campos extraídos}}."""
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.getLogger("dspy_embargos").warning(f"No se pudo leer checkpoint {ruta}: {e}")
            return {}
    return {}


def guardar_checkpoint(ruta: str, data: Dict[str, Any]):
    """Guarda el estado actual del checkpoint de forma atómica."""
    ruta_tmp = ruta + ".tmp"
    with open(ruta_tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if os.path.exists(ruta):
        os.remove(ruta)
    os.rename(ruta_tmp, ruta)


# ---------------------------------------------------------------------------
# Post-proceso: expandir múltiples embargados a filas individuales
# ---------------------------------------------------------------------------

CAMPOS_POR_PERSONA = ["nombre_embargado", "dni", "cuit_cuil"]
CAMPOS_COMPARTIDOS = ["monto_total", "monto_contexto", "cuenta"]
TODOS_LOS_CAMPOS = ["numero_archivo", "id", "nombre"] + CAMPOS_POR_PERSONA + CAMPOS_COMPARTIDOS


def expandir_embargados(resultado: Dict[str, Any], metadatos: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Si el resultado contiene múltiples embargados separados por '|' en nombre_embargado,
    genera una fila individual por cada persona embargada, alineando dni y cuit_cuil.
    Los campos compartidos (monto_total, monto_contexto, cuenta) se replican.

    Args:
        resultado: Dict con campos extraídos (nombre_embargado, dni, cuit_cuil, etc.)
        metadatos: Dict con metadatos del documento (numero_archivo, id, nombre)

    Returns:
        Lista de dicts, uno por cada persona embargada.
    """
    nombre_raw = str(resultado.get("nombre_embargado", "") or "").strip()
    if not nombre_raw:
        # Fila única con lo que haya
        fila = {**metadatos}
        for campo in CAMPOS_POR_PERSONA + CAMPOS_COMPARTIDOS:
            fila[campo] = str(resultado.get(campo, "") or "").strip()
        return [fila]

    # Separar por pipe '|'
    nombres = [n.strip() for n in nombre_raw.split("|") if n.strip()]
    num_personas = len(nombres)
    if num_personas == 0:
        num_personas = 1
        nombres = [""]

    # Procesar campos por persona
    valores_por_persona: Dict[str, List[str]] = {
        "nombre_embargado": nombres
    }

    for campo in ["dni", "cuit_cuil"]:
        val_raw = str(resultado.get(campo, "") or "").strip()
        if "|" in val_raw:
            partes = [p.strip() for p in val_raw.split("|")]
            # Si coincide la cantidad
            if len(partes) == num_personas:
                valores_por_persona[campo] = partes
            elif len(partes) < num_personas:
                # Rellenar con vacíos
                valores_por_persona[campo] = partes + [""] * (num_personas - len(partes))
            else:
                valores_por_persona[campo] = partes[:num_personas]
        else:
            # Si hay un único valor y varias personas, solo se lo asignamos al primero si num_personas > 1
            # salvo que num_personas sea 1
            if num_personas == 1:
                valores_por_persona[campo] = [val_raw]
            else:
                valores_por_persona[campo] = [val_raw] + [""] * (num_personas - 1)

    # Construir filas
    filas = []
    for i in range(num_personas):
        fila = {**metadatos}
        for campo in CAMPOS_POR_PERSONA:
            fila[campo] = valores_por_persona[campo][i]
        for campo in CAMPOS_COMPARTIDOS:
            fila[campo] = str(resultado.get(campo, "") or "").strip()
        filas.append(fila)

    return filas


def escribir_csv_salida(ruta_output: str, filas: List[Dict[str, Any]]):
    """Escribe las filas al CSV de salida con delimitador punto y coma y UTF-8-sig."""
    os.makedirs(os.path.dirname(os.path.abspath(ruta_output)), exist_ok=True)
    with open(ruta_output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TODOS_LOS_CAMPOS, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        for fila in filas:
            writer.writerow(fila)
