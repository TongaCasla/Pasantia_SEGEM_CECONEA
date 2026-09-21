"""
dataset.py - Carga, preparación y división del dataset supervisado para DSPy.
"""

import os
import csv
import random
import logging
from typing import List, Dict, Any, Tuple, Optional
import dspy

logger = logging.getLogger("dspy_embargos")


def cargar_textos_completos(ruta_frag_con_texto: str) -> Dict[str, Dict[str, str]]:
    """
    Carga el archivo frag_con_texto.csv y retorna un diccionario indexado por 'id':
    {doc_id: {"texto_completo": str, "nombre": str, "numero_archivo": str}}
    """
    if not os.path.exists(ruta_frag_con_texto):
        logger.warning(f"Archivo frag_con_texto no encontrado: {ruta_frag_con_texto}")
        return {}

    resultado = {}
    with open(ruta_frag_con_texto, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            doc_id = str(row.get("id", "")).strip()
            if not doc_id or doc_id in resultado:
                continue
            
            texto = str(row.get("texto_completo", "")).strip()
            if texto.startswith('"') and texto.endswith('"'):
                texto = texto[1:-1]
            texto = texto.replace('""', '"')

            resultado[doc_id] = {
                "texto_completo": texto,
                "nombre": str(row.get("nombre", "")).strip(),
                "numero_archivo": str(row.get("numero_archivo", "")).strip()
            }
    return resultado


def cargar_bd_supervisada(
    ruta_csv: str,
    ruta_frag_con_texto: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Lee bd_supervisada_embargos_actualizada.csv, agrupa por 'id' para unir registros
    con múltiples embargados usando '|', y opcionalmente enriquece con 'texto_completo'.

    Retorna una lista de diccionarios, uno por ID único.
    """
    if not os.path.exists(ruta_csv):
        raise FileNotFoundError(f"Archivo supervisado no encontrado: {ruta_csv}")

    # Cargar textos completos si se especificó el archivo
    mapa_textos = cargar_textos_completos(ruta_frag_con_texto) if ruta_frag_con_texto else {}

    # Agrupar filas por ID preservando orden
    grupos_por_id: Dict[str, List[Dict[str, str]]] = {}
    
    with open(ruta_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            doc_id = str(row.get("id", "")).strip()
            if not doc_id:
                continue
            if doc_id not in grupos_por_id:
                grupos_por_id[doc_id] = []
            grupos_por_id[doc_id].append(row)

    documentos = []
    for doc_id, filas in grupos_por_id.items():
        # Procesar campos por persona
        nombres_embargados = []
        dnis = []
        cuits = []

        for f in filas:
            nom = str(f.get("embargado", "") or "").strip()
            if nom.lower() in ("nan", "none", "null"):
                nom = ""
            dni = str(f.get("dni", "") or "").strip()
            if dni.lower() in ("nan", "none", "null"):
                dni = ""
            cuit = str(f.get("cuit_cuil", "") or "").strip()
            if cuit.lower() in ("nan", "none", "null"):
                cuit = ""

            nombres_embargados.append(nom)
            dnis.append(dni)
            cuits.append(cuit)

        nombre_embargado_str = " | ".join(nombres_embargados)
        dni_str = " | ".join(dnis)
        cuit_str = " | ".join(cuits)

        # Campos compartidos del documento (tomamos el primero no vacío)
        def primer_valor(campo: str) -> str:
            for f in filas:
                val = str(f.get(campo, "") or "").strip()
                if val and val.lower() not in ("nan", "none", "null"):
                    return val
            return ""

        contexto = primer_valor("contexto")
        monto_total = primer_valor("monto_total")
        cuenta = primer_valor("cuenta")
        numero_archivo = primer_valor("numero_archivo")
        nombre_archivo = primer_valor("nombre_archivo")

        # Texto completo si está disponible
        info_extra = mapa_textos.get(doc_id, {})
        texto_completo = info_extra.get("texto_completo", "")
        if not nombre_archivo:
            nombre_archivo = info_extra.get("nombre", "")
        if not numero_archivo:
            numero_archivo = info_extra.get("numero_archivo", "")

        doc = {
            "id": doc_id,
            "numero_archivo": numero_archivo,
            "nombre": nombre_archivo,
            "nombre_embargado": nombre_embargado_str,
            "dni": dni_str,
            "cuit_cuil": cuit_str,
            "monto_total": monto_total,
            "monto_contexto": "",  # La BD supervisada no tiene columna separada de fragmento de monto
            "cuenta": cuenta,
            "contexto": contexto,
            "texto_completo": texto_completo,
            "es_multiple": len(filas) > 1,
            "cantidad_embargados": len(filas),
        }
        documentos.append(doc)

    logger.info(
        f"BD supervisada cargada: {len(documentos)} documentos únicos "
        f"({sum(1 for d in documentos if d['es_multiple'])} con múltiples embargados)"
    )
    return documentos


def crear_ejemplos_dspy(
    documentos: List[Dict[str, Any]],
    campo_documento: str = "contexto"
) -> List[dspy.Example]:
    """
    Convierte una lista de documentos procesados en objetos dspy.Example
    con el input 'documento' y los campos de salida esperados.
    """
    ejemplos = []
    for doc in documentos:
        texto = doc.get(campo_documento, "")
        if not texto:
            # Si el campo solicitado está vacío, probar con el alternativo
            alt = "texto_completo" if campo_documento == "contexto" else "contexto"
            texto = doc.get(alt, "")

        ex = dspy.Example(
            documento=texto,
            nombre_embargado=doc.get("nombre_embargado", ""),
            dni=doc.get("dni", ""),
            cuit_cuil=doc.get("cuit_cuil", ""),
            monto_total=doc.get("monto_total", ""),
            monto_contexto=doc.get("monto_contexto", ""),
            cuenta=doc.get("cuenta", ""),
            # Metadatos para trazabilidad
            doc_id=doc.get("id", ""),
            numero_archivo=doc.get("numero_archivo", ""),
            nombre=doc.get("nombre", ""),
            es_multiple=doc.get("es_multiple", False),
        ).with_inputs("documento")

        ejemplos.append(ex)

    return ejemplos


def split_dataset(
    ejemplos: List[dspy.Example],
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
    seed: int = 42,
    priorizar_multiples_en_train: bool = True
) -> Tuple[List[dspy.Example], List[dspy.Example], List[dspy.Example]]:
    """
    Divide los ejemplos en conjuntos train, val y test respetando las proporciones.
    Si priorizar_multiples_en_train es True, asigna los casos con múltiples embargados
    preferentemente al conjunto de entrenamiento.
    """
    total = len(ejemplos)
    if total == 0:
        return [], [], []

    rng = random.Random(seed)

    if priorizar_multiples_en_train:
        multiples = [e for e in ejemplos if getattr(e, "es_multiple", False)]
        simples = [e for e in ejemplos if not getattr(e, "es_multiple", False)]

        rng.shuffle(simples)

        # Calculamos tamaños deseados
        n_train = int(total * train_ratio)
        n_val = int(total * val_ratio)
        n_test = total - n_train - n_val

        # Meter todos los múltiples que quepan en train
        trainset = list(multiples)
        faltan_train = max(0, n_train - len(trainset))

        trainset.extend(simples[:faltan_train])
        restantes = simples[faltan_train:]

        valset = restantes[:n_val]
        testset = restantes[n_val:]

        rng.shuffle(trainset)
    else:
        indices = list(range(total))
        rng.shuffle(indices)

        n_train = int(total * train_ratio)
        n_val = int(total * val_ratio)

        trainset = [ejemplos[i] for i in indices[:n_train]]
        valset = [ejemplos[i] for i in indices[n_train:n_train + n_val]]
        testset = [ejemplos[i] for i in indices[n_train + n_val:]]

    logger.info(f"Split dataset: {len(trainset)} train, {len(valset)} val, {len(testset)} test")
    return trainset, valset, testset
