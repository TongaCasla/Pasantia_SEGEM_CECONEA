import os
import sys
import csv
import re
import unicodedata
import argparse

def cargar_palabras_clave(ruta_archivo):
    """
    Carga palabras clave desde un archivo de texto, una por línea.
    Ignora líneas vacías y comentarios que comiencen con '#'.
    """
    palabras = []
    if not os.path.exists(ruta_archivo):
        print(f"Advertencia: El archivo de palabras clave '{ruta_archivo}' no existe.", file=sys.stderr)
        return palabras
        
    with open(ruta_archivo, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line_cleaned = line.strip()
            if line_cleaned and not line_cleaned.startswith('#'):
                palabras.append(line_cleaned)
    return palabras

def normalizar_texto(texto):
    """
    Normaliza el texto: convierte a minúsculas y elimina acentos/diacríticos.
    Retorna el texto normalizado y una lista que mapea cada índice del texto
    normalizado al índice correspondiente en el texto original.
    """
    if not texto:
        return "", []
    
    norm_chars = []
    orig_indices = []
    
    for idx, char in enumerate(texto):
        nfd = unicodedata.normalize('NFD', char)
        for c in nfd:
            if unicodedata.category(c) != 'Mn':
                norm_chars.append(c.lower())
                orig_indices.append(idx)
                
    orig_indices.append(len(texto))
    return "".join(norm_chars), orig_indices

def buscar_palabras_clave(texto_original, palabras_clave):
    """
    Busca las palabras clave en el texto original (normalizando ambos).
    Retorna una lista de diccionarios con la información de las coincidencias.
    """
    if not texto_original or not palabras_clave:
        return []
        
    norm_text, orig_indices = normalizar_texto(texto_original)
    coincidencias = []
    
    for palabra in palabras_clave:
        palabra_limpia = palabra.strip()
        if not palabra_limpia:
            continue
            
        palabra_norm = "".join(
            c.lower() for c in unicodedata.normalize('NFD', palabra_limpia)
            if unicodedata.category(c) != 'Mn'
        )
        
        if not palabra_norm:
            continue
            
        pattern = re.compile(re.escape(palabra_norm))
        for match in pattern.finditer(norm_text):
            norm_start = match.start()
            norm_end = match.end()
            
            orig_start = orig_indices[norm_start]
            orig_end = orig_indices[norm_end] if norm_end < len(orig_indices) else len(texto_original)
            
            coincidencias.append({
                'palabra_clave': palabra_limpia,
                'inicio': orig_start,
                'fin': orig_end,
                'texto_matcheado': texto_original[orig_start:orig_end]
            })
            
    # Ordenar coincidencias por posición de inicio en el texto original
    coincidencias.sort(key=lambda x: x['inicio'])
    return coincidencias

def extraer_fragmento(texto, inicio, fin, chars_antes, chars_despues):
    """
    Extrae la ventana de contexto alrededor de la coincidencia.
    Retorna el fragmento y las posiciones de inicio/fin correspondientes.
    """
    inicio_frag = max(0, inicio - chars_antes)
    fin_frag = min(len(texto), fin + chars_despues)
    fragmento = texto[inicio_frag:fin_frag]
    return fragmento, inicio_frag, fin_frag

def desescapar_texto(texto):
    """
    Limpia y desescapa el texto proveniente de un campo CSV.
    """
    if not texto:
        return ""
    
    # Reemplazar saltos de línea de Windows a estándar de Unix
    texto = texto.replace('\r\n', '\n')
    
    # Convertir comillas dobles internas escapadas ("" -> ")
    texto_desescapado = texto.replace('""', '"')
    
    # Si el campo está envuelto en comillas dobles, removerlas
    stripped = texto_desescapado.strip()
    if stripped.startswith('"') and stripped.endswith('"'):
        texto_desescapado = stripped[1:-1]
        
    return texto_desescapado

def buscar_indice_columna(headers, nombre_esperado, default_index):
    """
    Busca de forma flexible y sensible a minúsculas el índice de una columna.
    """
    nombre_esperado_lower = nombre_esperado.lower()
    for idx, header in enumerate(headers):
        if header.strip().lower() == nombre_esperado_lower:
            return idx
    for idx, header in enumerate(headers):
        if nombre_esperado_lower in header.strip().lower():
            return idx
    return default_index

def procesar_csv(ruta_csv, columna_texto, ruta_palabras, chars_antes, chars_despues, ruta_salida):
    palabras_clave = cargar_palabras_clave(ruta_palabras)
    if not palabras_clave:
        print("Error: No se pudieron cargar palabras clave. Abortando.", file=sys.stderr)
        sys.exit(1)
        
    if not os.path.exists(ruta_csv):
        print(f"Error: El archivo de entrada '{ruta_csv}' no existe.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Cargadas {len(palabras_clave)} palabras clave.")
    print(f"Procesando '{ruta_csv}'...")
    
    registros_creados = 0
    documentos_procesados = 0
    documentos_con_match = 0
    
    with open(ruta_csv, mode='r', encoding='utf-8-sig', newline='') as f_in:
        # Detectar delimitador leyendo las primeras líneas
        primera_linea = f_in.readline()
        f_in.seek(0)
        
        delimiter = ';'
        if ';' in primera_linea and primera_linea.count(';') > primera_linea.count(','):
            delimiter = ';'
        elif '\t' in primera_linea and primera_linea.count('\t') > primera_linea.count(','):
            delimiter = '\t'
        elif ',' in primera_linea:
            delimiter = ','
            
        reader = csv.reader(f_in, delimiter=delimiter)
        headers = next(reader, None)
        
        if not headers:
            print("Error: El archivo CSV está vacío.", file=sys.stderr)
            sys.exit(1)
            
        idx_numero = buscar_indice_columna(headers, 'numero_archivo', 0)
        idx_id = buscar_indice_columna(headers, 'id', 1)
        idx_nombre = buscar_indice_columna(headers, 'nombre', 2)
        idx_texto = buscar_indice_columna(headers, columna_texto, -1)
        
        if idx_texto == -1 or idx_texto >= len(headers):
            # Intentar buscar texto_limpio o texto como fallback
            idx_texto = buscar_indice_columna(headers, 'texto_limpio', -1)
            if idx_texto == -1:
                idx_texto = buscar_indice_columna(headers, 'texto', -1)
                
            if idx_texto == -1 or idx_texto >= len(headers):
                print(f"Error: No se encontró la columna de texto '{columna_texto}' en el CSV.", file=sys.stderr)
                sys.exit(1)
                
        # Abrir archivo de salida para escribir
        with open(ruta_salida, mode='w', encoding='utf-8-sig', newline='') as f_out:
            writer = csv.writer(f_out, delimiter=';')
            # Escribir cabecera
            writer.writerow([
                'numero_archivo',
                'id',
                'nombre',
                'contador_interno',
                'palabra_clave',
                'fragmento',
                'posicion_inicio',
                'posicion_fin',
                'inicio_fragmento',
                'fin_fragmento'
            ])
            
            for row in reader:
                if not row:
                    continue
                    
                documentos_procesados += 1
                
                num_archivo = row[idx_numero].strip() if idx_numero < len(row) else ""
                doc_id = row[idx_id].strip() if idx_id < len(row) else ""
                nombre = row[idx_nombre].strip() if idx_nombre < len(row) else ""
                
                texto_raw = row[idx_texto] if idx_texto < len(row) else ""
                texto = desescapar_texto(texto_raw)
                
                coincidencias = buscar_palabras_clave(texto, palabras_clave)
                
                if coincidencias:
                    documentos_con_match += 1
                    for match_idx, match in enumerate(coincidencias, start=1):
                        fragmento, inicio_frag, fin_frag = extraer_fragmento(
                            texto, 
                            match['inicio'], 
                            match['fin'], 
                            chars_antes, 
                            chars_despues
                        )
                        
                        writer.writerow([
                            num_archivo,
                            doc_id,
                            nombre,
                            match_idx,
                            match['palabra_clave'],
                            fragmento,
                            match['inicio'],
                            match['fin'],
                            inicio_frag,
                            fin_frag
                        ])
                        registros_creados += 1
                        
    print("\n--- Resumen de ejecución ---")
    print(f"Documentos procesados: {documentos_procesados}")
    print(f"Documentos con coincidencias: {documentos_con_match}")
    print(f"Registros de fragmentos generados: {registros_creados}")
    print(f"Archivo de salida guardado en: '{ruta_salida}'")

def main():
    parser = argparse.ArgumentParser(
        description="Extrae fragmentos de texto de embargos a partir de un CSV usando palabras clave."
    )
    parser.add_argument(
        "input",
        help="Ruta al CSV de entrada"
    )
    parser.add_argument(
        "-o", "--output",
        default="output_embargos.csv",
        help="Ruta al CSV de salida (default: output_embargos.csv)"
    )
    parser.add_argument(
        "-c", "--columna",
        default="texto_limpio",
        help="Nombre de la columna del CSV que contiene el texto (default: texto_limpio)"
    )
    parser.add_argument(
        "-k", "--keywords",
        default="palabras_clave.txt",
        help="Ruta al archivo de palabras clave (default: palabras_clave.txt)"
    )
    parser.add_argument(
        "-a", "--antes",
        type=int,
        default=200,
        help="Caracteres a extraer antes de la coincidencia (default: 200)"
    )
    parser.add_argument(
        "-p", "--despues",
        type=int,
        default=200,
        help="Caracteres a extraer después de la coincidencia (default: 200)"
    )
    
    args = parser.parse_args()
    
    procesar_csv(
        ruta_csv=args.input,
        columna_texto=args.columna,
        ruta_palabras=args.keywords,
        chars_antes=args.antes,
        chars_despues=args.despues,
        ruta_salida=args.output
    )

if __name__ == "__main__":
    main()
