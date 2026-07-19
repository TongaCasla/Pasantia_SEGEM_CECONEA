#!/usr/bin/env python3
"""
Script para procesar CSV y generar JSON jerárquico agrupado por documento,
con separación de nombres y apellidos para etiquetas tipo 'persona' usando el modelo
de PII GLiNER2 (fastino/gliner2-privacy-filter-PII-multi) ejecutado localmente (ej. en Colab).

Instrucciones para Google Colab:
------------------------------
1. Instalar las dependencias en una celda de Colab:
   !pip install gliner2 torch

2. Subir este script y el archivo CSV a procesar a Colab (o clonar tu repositorio de GitHub).
3. Ejecutar el script:
   !python separacion_nombres_colab.py -i <ruta_entrada.csv> -o <ruta_salida.json>
"""
import sys
import argparse
import json
import csv
import time
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

# Configurar la codificación de la consola para evitar UnicodeEncodeError en Windows/Linux
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


def cargar_cache(cache_path: str) -> Dict[str, Dict]:
    """Cargar cache de nombres ya procesados."""
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def guardar_cache(cache_path: str, cache_data: Dict[str, Dict]):
    """Guardar cache actualizada."""
    Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)


def separar_nombre_apellido_gliner(
    model,
    nombres: List[str],
    cache: Dict[str, Dict],
    batch_size: int = 32,
    threshold: float = 0.4
) -> Tuple[Dict[str, Dict], bool]:
    """
    Separar nombres y apellidos usando el modelo GLiNER2 en lotes con fallback secuencial.
    
    Args:
        model: Instancia del modelo GLiNER2 cargado
        nombres: Lista de nombres únicos para separar
        cache: Cache actual con nombres ya procesados
        batch_size: Tamaño de lote para procesar
        threshold: Umbral de confianza para la detección de entidades
    
    Returns:
        Tuple[Dict[str, Dict], bool]: Diccionario de caché actualizado y flag de éxito
    """
    if not nombres:
        return cache, True
    
    # Filtrar nombres que no están en la cache
    nombres_por_separar = [n for n in nombres if n not in cache]
    
    if not nombres_por_separar:
        print("✅ Todos los nombres ya están procesados en cache.")
        return cache, True
    
    print(f"🔍 Procesando {len(nombres_por_separar)} nombres únicos con GLiNER2 (lotes de {batch_size}, threshold {threshold})...")
    
    cache_actualizada = dict(cache)
    all_success = True
    
    # Etiquetas de entidad para extraer
    labels = ["first_name", "middle_name", "last_name"]
    
    # Dividir nombres_por_separar en lotes de tamaño batch_size
    for idx in range(0, len(nombres_por_separar), batch_size):
        lote = nombres_por_separar[idx:idx + batch_size]
        print(f"📦 Procesando lote {idx // batch_size + 1}/{(len(nombres_por_separar) - 1) // batch_size + 1} ({len(lote)} nombres)...")
        
        resultados_lote = []
        lote_success = False
        
        # Intentar procesamiento por lotes (batch extraction)
        try:
            # En la biblioteca gliner2, extract_entities acepta una lista de textos
            batch_predictions = model.extract_entities(
                lote,
                labels=labels,
                threshold=threshold
            )
            
            # Verificar que el resultado sea una lista y tenga el mismo tamaño que el lote
            if isinstance(batch_predictions, list) and len(batch_predictions) == len(lote):
                resultados_lote = batch_predictions
                lote_success = True
            else:
                print("⚠️ El formato del lote predicho no es el esperado. Se utilizará el fallback secuencial para este lote.")
        except Exception as e:
            print(f"⚠️ Error en predicción por lote ({e}). Se utilizará el fallback secuencial para este lote.")
            
        # Fallback secuencial (uno por uno) si el lote falló
        if not lote_success:
            resultados_lote = []
            for nombre in lote:
                try:
                    ents = model.extract_entities(
                        nombre,
                        labels=labels,
                        threshold=threshold
                    )
                    resultados_lote.append(ents)
                except Exception as e:
                    print(f"❌ Error al extraer entidades para '{nombre}': {e}")
                    resultados_lote.append([])
                    all_success = False
                    
        # Mapear las entidades extraídas a la caché
        for nombre, entities in zip(lote, resultados_lote):
            # Ordenar entidades detectadas por su posición inicial (start) para preservar orden
            try:
                sorted_entities = sorted(entities, key=lambda x: x.get("start", 0))
            except Exception:
                sorted_entities = entities
                
            first_names = []
            last_names = []
            
            for ent in sorted_entities:
                text_val = ent.get("text", "").strip()
                label_val = ent.get("label", "")
                
                # Mapear nombres a primer/segundo nombre, y apellidos a apellidos
                if label_val in ("first_name", "middle_name"):
                    first_names.append(text_val)
                elif label_val == "last_name":
                    last_names.append(text_val)
            
            # Formatear el resultado final de separación
            if first_names or last_names:
                nombre_sep = " ".join(first_names)
                apellido_sep = " ".join(last_names)
                
                # Si una de las partes quedó vacía debido a problemas de detección, pero el nombre original
                # tenía contenido, evitar dejar ambos vacíos
                if not nombre_sep and not apellido_sep:
                    nombre_sep = ""
                    apellido_sep = nombre
            else:
                # Fallback por defecto si no detectó nada (según prompt: nombre vacío y todo en apellido)
                nombre_sep = ""
                apellido_sep = nombre
                
            cache_actualizada[nombre] = {
                "nombre": nombre_sep,
                "apellido": apellido_sep
            }
            
    return cache_actualizada, all_success


def procesar_csv(input_file: str) -> Dict[str, Any]:
    """
    Leer CSV y agrupar entidades por documento y por id_etiqueta.
    
    Args:
        input_file: Ruta al archivo CSV de entrada
    
    Returns:
        Diccionario con la estructura agrupada de documentos y sus entidades.
    """
    print(f"📂 Leyendo archivo CSV: {input_file}")
    
    documentos = {}
    
    with open(input_file, 'r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f, delimiter=';')
        
        for row in reader:
            id_doc = row["id"].strip()
            if not id_doc:
                continue
                
            if id_doc not in documentos:
                numero_archivo_val = row["numero_archivo"].strip()
                documentos[id_doc] = {
                    "numero_archivo": int(numero_archivo_val) if numero_archivo_val else 0,
                    "id": id_doc,
                    "nombre_archivo": row["nombre_archivo"].strip(),
                    "clasificacion": row["clasificacion"].strip(),
                    "texto_limpio": row["texto_limpio"],
                    "entidades": {}  # id_etiqueta (int) -> entidad dict
                }
            
            id_etiqueta_val = row["id_etiqueta"].strip()
            id_etiqueta = int(id_etiqueta_val) if id_etiqueta_val else 0
            
            etiqueta = row["etiqueta"].strip()
            if not etiqueta:
                continue
                
            if id_etiqueta not in documentos[id_doc]["entidades"]:
                documentos[id_doc]["entidades"][id_etiqueta] = {
                    "id_etiqueta": id_etiqueta,
                    "etiqueta": etiqueta,
                    "valor_referencia": row["valor_referencia"].strip(),
                    "variantes": []
                }
            
            id_variante_val = row["id_variante"].strip()
            variante_data = {
                "id_variante": int(id_variante_val) if id_variante_val else 0,
                "valor": row["valor"].strip(),
                "metodo": row["metodo"].strip(),
                "span_inicio": int(row["span_inicio"]) if row["span_inicio"].strip() else 0,
                "span_fin": int(row["span_fin"]) if row["span_fin"].strip() else 0
            }
            documentos[id_doc]["entidades"][id_etiqueta]["variantes"].append(variante_data)
            
    return documentos


def generar_json_salida(documentos: Dict[str, Any], cache: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """
    Generar JSON jerárquico con estructura final y separación de nombres aplicada.
    
    Args:
        documentos: Diccionario agrupado por documento
        cache: Cache actualizada con separaciones de nombres
    
    Returns:
        Lista de documentos estructurada según especificación.
    """
    resultado_json = []
    
    for id_doc, doc_data in documentos.items():
        doc_json = {
            "numero_archivo": doc_data["numero_archivo"],
            "id": doc_data["id"],
            "nombre_archivo": doc_data["nombre_archivo"],
            "clasificacion": doc_data["clasificacion"],
            "texto_limpio": doc_data["texto_limpio"],
            "entidades": []
        }
        
        # Ordenar entidades por id_etiqueta
        entidades_ordenadas = sorted(doc_data["entidades"].items())
        
        for id_etiqueta, entidad in entidades_ordenadas:
            etiqueta = entidad["etiqueta"]
            val_ref_orig = entidad["valor_referencia"]
            
            if etiqueta == "persona":
                sep_ref = cache.get(val_ref_orig, {"nombre": "", "apellido": val_ref_orig})
                valor_referencia = {
                    "nombre": sep_ref.get("nombre", "").strip(),
                    "apellido": sep_ref.get("apellido", val_ref_orig).strip()
                }
            else:
                valor_referencia = val_ref_orig
                
            entidad_json = {
                "id_etiqueta": entidad["id_etiqueta"],
                "etiqueta": etiqueta,
                "valor_referencia": valor_referencia,
                "variantes": []
            }
            
            # Ordenar variantes por id_variante
            variantes_ordenadas = sorted(entidad["variantes"], key=lambda v: v["id_variante"])
            
            for var in variantes_ordenadas:
                var_val_orig = var["valor"]
                if etiqueta == "persona":
                    sep_val = cache.get(var_val_orig, {"nombre": "", "apellido": var_val_orig})
                    valor_variante = {
                        "nombre": sep_val.get("nombre", "").strip(),
                        "apellido": sep_val.get("apellido", var_val_orig).strip()
                    }
                else:
                    valor_variante = var_val_orig
                    
                entidad_json["variantes"].append({
                    "id_variante": var["id_variante"],
                    "valor": valor_variante,
                    "metodo": var["metodo"],
                    "span_inicio": var["span_inicio"],
                    "span_fin": var["span_fin"]
                })
                
            doc_json["entidades"].append(entidad_json)
            
        resultado_json.append(doc_json)
        
    return resultado_json


def main():
    parser = argparse.ArgumentParser(
        description="Procesa CSV y genera JSON jerárquico agrupado por documento con separación de nombres (usando GLiNER2 en Colab)"
    )
    
    parser.add_argument("-i", "--input", required=True, help="Ruta al archivo CSV de entrada")
    parser.add_argument("-o", "--output", required=True, help="Ruta al archivo JSON de salida")
    parser.add_argument("--model", default="fastino/gliner2-privacy-filter-PII-multi", 
                        help="Modelo GLiNER2 a descargar y utilizar (default: fastino/gliner2-privacy-filter-PII-multi)")
    parser.add_argument("--batch-size", type=int, default=32, help="Tamaño del lote de procesamiento (default: 32)")
    parser.add_argument("--cache", default="_cache_nombres.json", help="Ruta al archivo JSON de cache (default: _cache_nombres.json)")
    parser.add_argument("--threshold", type=float, default=0.4, 
                        help="Umbral de confianza para la detección de entidades de nombres (default: 0.4)")
    
    args = parser.parse_args()
    
    # Verificar archivos de entrada
    if not Path(args.input).exists():
        print(f"❌ Error: El archivo de entrada no existe: {args.input}")
        return 1
    
    # Cargar cache inicial
    cache_path = Path(args.cache)
    cache_data = cargar_cache(str(cache_path))
    
    try:
        print("📝 Procesando archivo CSV...")
        documentos = procesar_csv(args.input)
        
        # Obtener lista de todos los nombres de tipo "persona" únicos
        all_nombres_personas = set()
        for doc_id, doc_data in documentos.items():
            for id_etiqueta, entidad in doc_data["entidades"].items():
                if entidad["etiqueta"] == "persona":
                    val_ref = entidad["valor_referencia"].strip()
                    if val_ref:
                        all_nombres_personas.add(val_ref)
                    for variante in entidad["variantes"]:
                        valor_variante = variante["valor"].strip()
                        if valor_variante:
                            all_nombres_personas.add(valor_variante)
        
        print(f"📋 Total de nombres 'persona' únicos encontrados: {len(all_nombres_personas)}")
        
        # Filtrar nombres que ya están en cache
        nombres_por_separar = [n for n in all_nombres_personas if n not in cache_data]
        nombres_en_cache = len(all_nombres_personas) - len(nombres_por_separar)
        
        print(f"✅ Nombres encontrados en cache: {nombres_en_cache}")
        print(f"🔹 Nombres por procesar con GLiNER2: {len(nombres_por_separar)}")
        
        # Si hay nombres por separar, cargar e inicializar el modelo
        if nombres_por_separar:
            print("🚀 Cargando librerías de Machine Learning (torch, gliner2)...")
            try:
                import torch
                from gliner2 import GLiNER2
            except ImportError as e:
                print(f"❌ Error de Importación: {e}")
                print("Por favor, asegúrate de instalar las dependencias requeridas:")
                print("pip install gliner2 torch")
                return 1
            
            # Detectar dispositivo
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"⚙️ Dispositivo de ejecución detectado: {device.upper()}")
            
            print(f"📥 Descargando/Cargando el modelo '{args.model}'...")
            model = GLiNER2.from_pretrained(args.model)
            model = model.to(device)
            
            # Procesar con el modelo
            cache_data_actualizada, _ = separar_nombre_apellido_gliner(
                model=model,
                nombres=sorted(list(all_nombres_personas)),
                cache=cache_data,
                batch_size=args.batch_size,
                threshold=args.threshold
            )
            
            # Guardar cache actualizada
            guardar_cache(str(cache_path), cache_data_actualizada)
            print(f"💾 Cache guardada exitosamente en: {cache_path}")
            cache_data = cache_data_actualizada
            
        # Generar JSON de salida con la separación aplicada
        json_salida = generar_json_salida(documentos, cache_data)
        
    except Exception as e:
        print(f"❌ Error durante el procesamiento: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Guardar resultado en archivo JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(json_salida, f, ensure_ascii=False, indent=2)
    
    print(f"✅ JSON generado exitosamente en: {output_path}")
    print("✅ Procesamiento completado con éxito!")
    return 0


if __name__ == "__main__":
    exit(main())
