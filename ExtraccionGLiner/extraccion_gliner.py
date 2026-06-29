#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script para la extracción de entidades de Información Personal Identificable (PII)
utilizando el modelo GLiNER (fastino/gliner2-privacy-filter-PII-multi).
Diseñado para ejecutarse en entornos locales o de Google Colab.
"""

import os
import sys
import json
import argparse
import pandas as pd
from tqdm import tqdm
import torch
from gliner2 import GLiNER2

# Configurar UTF-8 para consola si es necesario
if sys.platform.startswith('win'):
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Lista de etiquetas predefinidas para la extracción de PII
PII_LABELS = [
    "person", 
    "national_id_number", 
    "government_id", 
    "tax_id", 
    "bank_account", 
    "account_number"
]

def parse_arguments():
    """
    Configura y parsea los argumentos de la línea de comandos.
    """
    parser = argparse.ArgumentParser(
        description="Extracción de entidades PII desde JSON/CSV usando GLiNER."
    )
    parser.add_argument(
        "--input", 
        required=True, 
        help="Ruta al archivo de entrada (JSON o CSV)."
    )
    parser.add_argument(
        "--output", 
        required=True, 
        help="Ruta al directorio de salida donde se guardarán los resultados."
    )
    parser.add_argument(
        "--text-column", 
        default="texto_limpio", 
        help="Nombre de la columna/campo que contiene el texto a analizar (default: 'texto_limpio')."
    )
    parser.add_argument(
        "--threshold", 
        type=float, 
        default=0.5, 
        help="Umbral de confianza para la detección de entidades (default: 0.5)."
    )
    parser.add_argument(
        "--chunk-size", 
        type=int, 
        default=1500, 
        help="Tamaño máximo de caracteres por fragmento de texto (para evitar truncamiento) (default: 1500)."
    )
    parser.add_argument(
        "--overlap", 
        type=int, 
        default=150, 
        help="Superposición en caracteres entre fragmentos (default: 150)."
    )
    return parser.parse_args()

def load_data(input_path, text_column):
    """
    Carga datos desde archivos CSV o JSON (incluyendo JSON Lines) de forma robusta.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"El archivo de entrada no existe en la ruta especificada: {input_path}")
    
    ext = os.path.splitext(input_path)[1].lower()
    records = []
    
    print(f"Cargando datos desde: {input_path} ...")
    
    if ext == '.csv':
        try:
            df = pd.read_csv(input_path)
            records = df.to_dict(orient='records')
        except Exception as e:
            raise ValueError(f"Error al leer el archivo CSV: {e}")
            
    elif ext == '.json':
        try:
            # Intento de cargar como JSON estándar (lista o diccionario)
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                records = data
            elif isinstance(data, dict):
                records = [data]
            else:
                raise ValueError("El archivo JSON debe contener una lista o un objeto.")
        except json.JSONDecodeError:
            # Si falla, intentar como JSON Lines (una línea por objeto)
            print("No se pudo decodificar como JSON estándar. Intentando cargar como JSON Lines...")
            try:
                with open(input_path, 'r', encoding='utf-8') as f:
                    records = [json.loads(line) for line in f if line.strip()]
            except Exception as e:
                raise ValueError(f"Error al leer el archivo como JSON Lines: {e}")
    else:
        raise ValueError(f"Formato de archivo '{ext}' no soportado. Debe ser .csv o .json")
    
    if not records:
        raise ValueError("El archivo de entrada está vacío.")
        
    print(f"Se cargaron {len(records)} registros en total.")
    
    # Filtrar registros válidos
    valid_records = []
    missing_text_count = 0
    
    for idx, r in enumerate(records):
        # Asegurar de tener un identificador
        if "id" not in r:
            r["id"] = f"gen_id_{idx}"
            
        text_val = r.get(text_column)
        if text_val is not None and isinstance(text_val, str) and text_val.strip():
            valid_records.append(r)
        else:
            missing_text_count += 1
            
    if not valid_records:
        raise ValueError(f"Ningún registro contiene la columna/campo de texto '{text_column}' con contenido válido.")
        
    if missing_text_count > 0:
        print(f"Advertencia: Se omitieron {missing_text_count} registros por no tener texto válido en '{text_column}'.")
        
    print(f"Registros listos para analizar: {len(valid_records)}")
    return valid_records

def chunk_text(text, max_chars=1500, overlap=150):
    """
    Divide el texto en fragmentos que se superponen, buscando cortes limpios.
    Devuelve una lista de tuplas (posicion_inicial_en_texto_original, texto_fragmento).
    """
    if len(text) <= max_chars:
        return [(0, text)]
    
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = start + max_chars
        if end >= text_len:
            chunks.append((start, text[start:]))
            break
            
        # Buscar un límite lógico (salto de línea, punto y espacio o espacio) en el solapamiento
        boundary = -1
        search_start = max(start, end - overlap)
        
        # 1. Probar salto de línea
        boundary = text.rfind('\n', search_start, end)
        if boundary == -1:
            # 2. Probar punto y espacio
            boundary = text.rfind('. ', search_start, end)
            if boundary != -1:
                boundary += 1  # Mantener el punto en el chunk actual
            else:
                # 3. Probar espacio simple
                boundary = text.rfind(' ', search_start, end)
                
        if boundary != -1 and boundary > start:
            chunk_end = boundary
        else:
            chunk_end = end
            
        chunks.append((start, text[start:chunk_end]))
        
        # Determinar el inicio del siguiente fragmento
        if boundary != -1:
            start = chunk_end + 1
        else:
            start = chunk_end - overlap
            if start <= chunks[-1][0]:  # Evitar bucles infinitos en casos extraños
                start = chunk_end
                
    return chunks

def process_records(records, model, labels, text_column, threshold, chunk_size, overlap):
    """
    Procesa todos los registros a través de GLiNER y extrae las entidades.
    """
    results = []
    
    print("\nIniciando extracción de entidades con GLiNER...")
    
    for r in tqdm(records, desc="Procesando documentos", unit="doc"):
        doc_id = r.get("id")
        nombre = r.get("nombre", "")
        clasificacion = r.get("clasificacion", "")
        full_text = r[text_column]
        
        # Chunking para textos largos
        chunks = chunk_text(full_text, max_chars=chunk_size, overlap=overlap)
        
        all_entities = []
        
        for start_offset, chunk in chunks:
            try:
                # Predecir entidades en el fragmento
                res = model.extract_entities(
                    chunk, 
                    labels, 
                    threshold=threshold, 
                    include_confidence=True, 
                    include_spans=True
                )
                entities_dict = res.get("entities", {})
                
                # Ajustar los offsets al texto original
                for ent_label, items in entities_dict.items():
                    for ent in items:
                        ent_adjusted = {
                            "text": ent["text"],
                            "label": ent_label,
                            "score": round(float(ent.get("confidence", 0.0)), 4),
                            "start": ent["start"] + start_offset,
                            "end": ent["end"] + start_offset
                        }
                        all_entities.append(ent_adjusted)
            except Exception as e:
                print(f"\nError al procesar fragmento en documento ID {doc_id}: {e}")
                
        # Deduplicar entidades redundantes causadas por la superposición de chunks
        unique_entities = {}
        for ent in all_entities:
            # Usamos start, end y label como clave única
            key = (ent["start"], ent["end"], ent["label"])
            if key not in unique_entities or ent["score"] > unique_entities[key]["score"]:
                unique_entities[key] = ent
                
        # Ordenar entidades por índice de inicio
        sorted_entities = sorted(list(unique_entities.values()), key=lambda x: x["start"])
        
        # Guardar resultado del registro
        results.append({
            "id": doc_id,
            "nombre": nombre,
            "clasificacion": clasificacion,
            "texto_analizado": full_text,
            "entities": sorted_entities
        })
        
    return results

def save_results(results, output_dir, input_filename):
    """
    Guarda los resultados estructurados tanto en formato JSON como en CSV (aplanado).
    """
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(input_filename)[0]
    
    json_path = os.path.join(output_dir, f"{base_name}_gliner_pii.json")
    csv_path = os.path.join(output_dir, f"{base_name}_gliner_pii.csv")
    
    # 1. Guardar JSON completo
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\nResultados estructurados JSON guardados en: {json_path}")
    except Exception as e:
        print(f"Error al guardar archivo JSON: {e}")
        
    # 2. Aplanar para guardar CSV
    csv_rows = []
    for r in results:
        doc_id = r["id"]
        nombre = r["nombre"]
        clasificacion = r["clasificacion"]
        
        if not r["entities"]:
            # Opcional: Si se quiere documentar que el archivo no tuvo entidades,
            # descomentar la línea de abajo. Por defecto, solo guardamos entidades encontradas.
            # csv_rows.append({
            #     "id": doc_id, "nombre": nombre, "clasificacion": clasificacion,
            #     "entity_text": "", "entity_label": "", "entity_score": 0.0,
            #     "start_char": -1, "end_char": -1
            # })
            pass
        else:
            for ent in r["entities"]:
                csv_rows.append({
                    "id": doc_id,
                    "nombre": nombre,
                    "clasificacion": clasificacion,
                    "entity_text": ent["text"],
                    "entity_label": ent["label"],
                    "entity_score": ent["score"],
                    "start_char": ent["start"],
                    "end_char": ent["end"]
                })
                
    try:
        if csv_rows:
            df = pd.DataFrame(csv_rows)
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"Resultados aplanados CSV guardados en: {csv_path}")
        else:
            # Crear un archivo CSV vacío con cabeceras si no hay entidades
            df = pd.DataFrame(columns=["id", "nombre", "clasificacion", "entity_text", "entity_label", "entity_score", "start_char", "end_char"])
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"No se detectaron entidades. Se creó archivo CSV de salida con cabeceras: {csv_path}")
    except Exception as e:
        print(f"Error al guardar archivo CSV: {e}")

def main():
    args = parse_arguments()
    
    # 1. Cargar Datos
    try:
        records = load_data(args.input, args.text_column)
    except Exception as e:
        print(f"Error al cargar los datos: {e}", file=sys.stderr)
        sys.exit(1)
        
    # 2. Configurar dispositivo de inferencia (GPU/CPU)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Dispositivo de ejecución de PyTorch: {device.upper()}")
    
    # 3. Cargar el Modelo GLiNER
    model_name = "fastino/gliner2-privacy-filter-PII-multi"
    print(f"Cargando modelo GLiNER '{model_name}' (esto puede tomar un momento)...")
    try:
        model = GLiNER2.from_pretrained(model_name, map_location=device)
    except Exception as e:
        print(f"Error al cargar el modelo GLiNER: {e}", file=sys.stderr)
        print("Asegúrate de tener conexión a internet y tener instaladas las dependencias del modelo.", file=sys.stderr)
        sys.exit(1)
        
    # 4. Procesar Registros
    results = process_records(
        records=records,
        model=model,
        labels=PII_LABELS,
        text_column=args.text_column,
        threshold=args.threshold,
        chunk_size=args.chunk_size,
        overlap=args.overlap
    )
    
    # 5. Guardar Resultados
    input_filename = os.path.basename(args.input)
    save_results(results, args.output, input_filename)
    
    print("\nProceso finalizado con éxito.")

if __name__ == "__main__":
    main()
