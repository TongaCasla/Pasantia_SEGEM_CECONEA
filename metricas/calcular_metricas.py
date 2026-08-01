import os
import sys
import argparse
import pandas as pd
import numpy as np
from thefuzz import fuzz
import matplotlib.pyplot as plt

# --- Valores por Defecto ---
DEFAULT_REFERENCIA = os.path.join("..", "final_solicitud.csv")
DEFAULT_GLINER2 = os.path.join("..", "resultados", "gliner2_output.csv")
DEFAULT_LARGE_V25 = os.path.join("..", "resultados", "large_v25_output.csv")
DEFAULT_PII_V1 = os.path.join("..", "resultados", "pii_v1_output.csv")

DEFAULT_OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
UMBRAL_SIMILITUD = 85          # percent
TOLERANCIA_LONGITUD = 3        # +/- 3 caracteres
ETIQUETAS_EVALUABLES = ["persona", "dni", "cuit_cuil", "cvu", "cbu"]
ETIQUETAS_OPCIONALES = ["alias", "persona_juridica"]
ETIQUETAS_EXCLUIDAS = ["monto", "rev_nombre"]


def clean_val(v):
    if pd.isna(v):
        return ""
    return str(v).strip()

def evaluar_modelo(df_ref, df_mod, umbral=UMBRAL_SIMILITUD, tol_len=TOLERANCIA_LONGITUD):
    """
    Realiza el matching 1 a 1 por documento entre la referencia y los resultados de un modelo.
    """
    ref_eval = df_ref[~df_ref['etiqueta'].isin(ETIQUETAS_EXCLUIDAS)].copy()
    
    # Listas para almacenar resultados detallados
    matches_list = []      # (doc_id, ref_idx, mod_idx, ref_etiqueta, ref_valor, mod_valor, match_type, score)
    extras_list = []       # (doc_id, mod_etiqueta, mod_valor)
    no_encontradas_list = [] # (doc_id, ref_etiqueta, ref_valor)
    opcionales_list = []   # (doc_id, ref_etiqueta, ref_valor, detectado, mod_valor)
    
    all_doc_ids = sorted(list(set(ref_eval['id'].unique()).union(set(df_mod['id'].unique()))))
    
    for doc_id in all_doc_ids:
        ref_doc = ref_eval[ref_eval['id'] == doc_id].copy()
        mod_doc = df_mod[df_mod['id'] == doc_id].copy()
        
        ref_matched = set()
        mod_matched = set()
        
        ref_records = ref_doc.to_dict('records')
        mod_records = mod_doc.to_dict('records')
        
        # 1. Matches exactos
        for r_idx, r in enumerate(ref_records):
            r_val = clean_val(r['valor'])
            r_val_lower = r_val.lower()
            
            for m_idx, m in enumerate(mod_records):
                if m_idx in mod_matched:
                    continue
                m_val = clean_val(m['valor'])
                if m_val.lower() == r_val_lower:
                    ref_matched.add(r_idx)
                    mod_matched.add(m_idx)
                    matches_list.append({
                        'id': doc_id,
                        'ref_etiqueta': r['etiqueta'],
                        'ref_valor': r_val,
                        'mod_etiqueta': m['etiqueta'],
                        'mod_valor': m_val,
                        'match_type': 'exacta',
                        'ratio': 100
                    })
                    break
                    
        # 2. Matches parciales (thefuzz)
        for r_idx, r in enumerate(ref_records):
            if r_idx in ref_matched:
                continue
            r_val = clean_val(r['valor'])
            r_val_lower = r_val.lower()
            
            best_m_idx = None
            best_ratio = 0
            best_m_val = ""
            best_m_etiq = ""
            
            for m_idx, m in enumerate(mod_records):
                if m_idx in mod_matched:
                    continue
                m_val = clean_val(m['valor'])
                m_val_lower = m_val.lower()
                
                # Tolerancia de longitud
                if abs(len(r_val_lower) - len(m_val_lower)) > tol_len:
                    continue
                
                ratio = fuzz.ratio(r_val_lower, m_val_lower)
                if ratio >= umbral and ratio > best_ratio:
                    best_ratio = ratio
                    best_m_idx = m_idx
                    best_m_val = m_val
                    best_m_etiq = m['etiqueta']
                    
            if best_m_idx is not None:
                ref_matched.add(r_idx)
                mod_matched.add(best_m_idx)
                matches_list.append({
                    'id': doc_id,
                    'ref_etiqueta': r['etiqueta'],
                    'ref_valor': r_val,
                    'mod_etiqueta': best_m_etiq,
                    'mod_valor': best_m_val,
                    'match_type': 'parcial',
                    'ratio': best_ratio
                })
                
        # Registramos las no encontradas y extras
        for r_idx, r in enumerate(ref_records):
            if r_idx not in ref_matched:
                r_val = clean_val(r['valor'])
                if r['etiqueta'] in ETIQUETAS_OPCIONALES:
                    opcionales_list.append({
                        'id': doc_id,
                        'etiqueta': r['etiqueta'],
                        'valor': r_val,
                        'detectado': False,
                        'mod_valor': None
                    })
                elif r['etiqueta'] in ETIQUETAS_EVALUABLES:
                    no_encontradas_list.append({
                        'id': doc_id,
                        'etiqueta': r['etiqueta'],
                        'valor': r_val
                    })
                    
        for m_idx, m in enumerate(mod_records):
            if m_idx not in mod_matched:
                extras_list.append({
                    'numero_archivo': m.get('numero_archivo'),
                    'id': doc_id,
                    'nombre_archivo': m.get('nombre_archivo'),
                    'clasificacion': m.get('clasificacion'),
                    'etiqueta': m.get('etiqueta'),
                    'valor': clean_val(m.get('valor')),
                    'span_inicio': m.get('span_inicio'),
                    'span_fin': m.get('span_fin'),
                    'score': m.get('score')
                })

        # Clasificar los matches opcionales para informe separado
        for m in matches_list:
            if m['id'] == doc_id and m['ref_etiqueta'] in ETIQUETAS_OPCIONALES:
                opcionales_list.append({
                    'id': doc_id,
                    'etiqueta': m['ref_etiqueta'],
                    'valor': m['ref_valor'],
                    'detectado': True,
                    'mod_valor': m['mod_valor']
                })
                
    df_matches = pd.DataFrame(matches_list)
    df_extras = pd.DataFrame(extras_list)
    df_no_enc = pd.DataFrame(no_encontradas_list)
    df_opcionales = pd.DataFrame(opcionales_list)
    
    return df_matches, df_extras, df_no_enc, df_opcionales

def calcular_resumen(df_ref, df_matches, df_extras, df_no_enc):
    # Total de referencia evaluable
    ref_eval = df_ref[df_ref['etiqueta'].isin(ETIQUETAS_EVALUABLES)]
    total_ref_eval = len(ref_eval)
    
    # Matches evaluables
    if not df_matches.empty:
        matches_eval = df_matches[df_matches['ref_etiqueta'].isin(ETIQUETAS_EVALUABLES)]
        n_exactas = len(matches_eval[matches_eval['match_type'] == 'exacta'])
        n_parciales = len(matches_eval[matches_eval['match_type'] == 'parcial'])
    else:
        n_exactas = 0
        n_parciales = 0
        
    n_detectadas = n_exactas + n_parciales
    n_no_enc = len(df_no_enc)
    n_extras = len(df_extras)
    
    precision = n_detectadas / (n_detectadas + n_extras) if (n_detectadas + n_extras) > 0 else 0.0
    recall = n_detectadas / total_ref_eval if total_ref_eval > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    resumen_global = {
        'total_ref': total_ref_eval,
        'exactas': n_exactas,
        'parciales': n_parciales,
        'total_detectadas': n_detectadas,
        'no_encontradas': n_no_enc,
        'extras': n_extras,
        'precision': precision,
        'recall': recall,
        'f1': f1
    }
    
    # Por etiqueta
    resumen_etiquetas = {}
    for etiq in ETIQUETAS_EVALUABLES:
        total_etiq_ref = len(ref_eval[ref_eval['etiqueta'] == etiq])
        if not df_matches.empty:
            m_etiq = df_matches[df_matches['ref_etiqueta'] == etiq]
            exact_e = len(m_etiq[m_etiq['match_type'] == 'exacta'])
            parc_e = len(m_etiq[m_etiq['match_type'] == 'parcial'])
        else:
            exact_e = 0
            parc_e = 0
        
        det_e = exact_e + parc_e
        no_enc_e = len(df_no_enc[df_no_enc['etiqueta'] == etiq]) if not df_no_enc.empty else 0
        
        rec_e = det_e / total_etiq_ref if total_etiq_ref > 0 else 0.0
        
        resumen_etiquetas[etiq] = {
            'total_ref': total_etiq_ref,
            'exactas': exact_e,
            'parciales': parc_e,
            'total_detectadas': det_e,
            'no_encontradas': no_enc_e,
            'recall': rec_e
        }
        
    return resumen_global, resumen_etiquetas

def generar_graficos(resumenes_globales, resumenes_etiquetas, graficos_dir):
    os.makedirs(graficos_dir, exist_ok=True)
    modelos = list(resumenes_globales.keys())
    
    # 1. Comparativa Global (Precision, Recall, F1)
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(modelos))
    width = 0.25
    
    precisions = [resumenes_globales[m]['precision'] * 100 for m in modelos]
    recalls = [resumenes_globales[m]['recall'] * 100 for m in modelos]
    f1s = [resumenes_globales[m]['f1'] * 100 for m in modelos]
    
    rects1 = ax.bar(x - width, precisions, width, label='Precision (%)', color='#2b5c8f')
    rects2 = ax.bar(x, recalls, width, label='Recall (%)', color='#d95f02')
    rects3 = ax.bar(x + width, f1s, width, label='F1-Score (%)', color='#7570b3')
    
    ax.set_ylabel('Porcentaje (%)')
    ax.set_title('Comparativa Global de Desempeño por Modelo')
    ax.set_xticks(x)
    ax.set_xticklabels(modelos)
    ax.legend(loc='lower right')
    ax.set_ylim(0, 105)
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    
    for rects in [rects1, rects2, rects3]:
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f'{height:.1f}%',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3),  
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=8)
                        
    plt.tight_layout()
    plt.savefig(os.path.join(graficos_dir, "comparativa_global.png"), dpi=300)
    plt.close()
    
    # 2. Detalle de Categorías (Exactas, Parciales, No encontradas, Extras)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(modelos))
    width = 0.2
    
    exactas = [resumenes_globales[m]['exactas'] for m in modelos]
    parciales = [resumenes_globales[m]['parciales'] for m in modelos]
    no_enc = [resumenes_globales[m]['no_encontradas'] for m in modelos]
    extras = [resumenes_globales[m]['extras'] for m in modelos]
    
    r1 = ax.bar(x - 1.5*width, exactas, width, label='Correctas (Exactas)', color='#2ca02c')
    r2 = ax.bar(x - 0.5*width, parciales, width, label='Detecciones Parciales', color='#bcbd22')
    r3 = ax.bar(x + 0.5*width, no_enc, width, label='No Encontradas (Error)', color='#d62728')
    r4 = ax.bar(x + 1.5*width, extras, width, label='Extras (Id. Errónea)', color='#ff7f0e')
    
    ax.set_ylabel('Cantidad de Entidades')
    ax.set_title('Desglose de Conteo por Categoría y Modelo')
    ax.set_xticks(x)
    ax.set_xticklabels(modelos)
    ax.legend(loc='upper right')
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    
    for rects in [r1, r2, r3, r4]:
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f'{height}',
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3),  
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=8)
                        
    plt.tight_layout()
    plt.savefig(os.path.join(graficos_dir, "detalle_categorias.png"), dpi=300)
    plt.close()
    
    # 3. Recall por Etiqueta
    fig, ax = plt.subplots(figsize=(11, 6))
    etiqs = ETIQUETAS_EVALUABLES
    x = np.arange(len(etiqs))
    width = 0.25
    
    for i, m in enumerate(modelos):
        recalls_e = [resumenes_etiquetas[m][e]['recall'] * 100 for e in etiqs]
        rects = ax.bar(x + (i - 1)*width, recalls_e, width, label=m)
        for rect in rects:
            height = rect.get_height()
            if height > 0:
                ax.annotate(f'{height:.0f}%',
                            xy=(rect.get_x() + rect.get_width() / 2, height),
                            xytext=(0, 3),
                            textcoords="offset points",
                            ha='center', va='bottom', fontsize=7)
                            
    ax.set_ylabel('Recall (%)')
    ax.set_title('Recall por Etiqueta y Modelo')
    ax.set_xticks(x)
    ax.set_xticklabels(etiqs)
    ax.legend(loc='upper right')
    ax.set_ylim(0, 110)
    ax.grid(axis='y', linestyle='--', alpha=0.5)
    
    plt.tight_layout()
    plt.savefig(os.path.join(graficos_dir, "recall_por_etiqueta.png"), dpi=300)
    plt.close()

def generar_reporte_markdown(resumenes_globales, resumenes_etiquetas, opcionales_dict, extras_dict, no_enc_dict, reporte_path, umbral, tol_len):
    md = []
    md.append("# Reporte de Evaluación de Métricas de Modelos PII / NER\n")
    md.append("Este reporte presenta la evaluación comparativa de tres modelos (**GLiNER2**, **Large_v25**, **PII_v1**) "
              "frente al archivo de referencia supervisada.\n")
    md.append(f"**Parámetros de Evaluación**: Umbral de Similitud Fuzzy = `{umbral}%` | Tolerancia Longitud = `±{tol_len} caracteres`\n")
    
    md.append("## 1. Resumen Ejecutivo\n")
    md.append("| Modelo | Precision (%) | Recall (%) | F1-Score (%) | Exactas | Parciales | No Encontradas | Extras |")
    md.append("|---|---|---|---|---|---|---|---|")
    for m, g in resumenes_globales.items():
        md.append(f"| **{m}** | {g['precision']*100:.2f}% | {g['recall']*100:.2f}% | {g['f1']*100:.2f}% | "
                  f"{g['exactas']} | {g['parciales']} | {g['no_encontradas']} | {g['extras']} |")
    md.append("\n")
    
    md.append("![Comparativa Global](graficos/comparativa_global.png)\n")
    
    md.append("## 2. Detalle de Categorías Globales\n")
    md.append("![Detalle Categorías](graficos/detalle_categorias.png)\n")
    first_model = list(resumenes_globales.keys())[0]
    total_ref_eval = resumenes_globales[first_model]['total_ref']
    md.append(f"- **Total Referencia Evaluable**: {total_ref_eval} entidades (persona, dni, cuit_cuil, cvu, cbu).")


    md.append("- **Correctas (Exactas)**: Coincidencia textual exacta de valor.")
    md.append(f"- **Detecciones Parciales**: Coincidencia por similitud (thefuzz >= {umbral}% y |diferencia longitud| <= {tol_len}).")
    md.append("- **No Encontradas (Error)**: Entidades de la referencia no detectadas por el modelo.")
    md.append("- **Extras (Id. Errónea)**: Entidades detectadas por el modelo que no existen en la referencia.\n")
    
    md.append("## 3. Métricas por Etiqueta\n")
    md.append("![Recall por Etiqueta](graficos/recall_por_etiqueta.png)\n")
    
    for etiq in ETIQUETAS_EVALUABLES:
        md.append(f"### Etiqueta: `{etiq}`")
        md.append("| Modelo | Total Ref | Exactas | Parciales | Total Detectadas | No Encontradas | Recall (%) |")
        md.append("|---|---|---|---|---|---|---|")
        for m in resumenes_globales.keys():
            e_stat = resumenes_etiquetas[m][etiq]
            md.append(f"| **{m}** | {e_stat['total_ref']} | {e_stat['exactas']} | {e_stat['parciales']} | "
                      f"{e_stat['total_detectadas']} | {e_stat['no_encontradas']} | {e_stat['recall']*100:.2f}% |")
        md.append("")
        
    md.append("## 4. Detección de Etiquetas Opcionales (`alias` y `persona_juridica`)\n")
    md.append("Las siguientes etiquetas no se penalizan si el modelo no las detecta, pero se contabilizan si hay coincidencia de valor:\n")
    md.append("| Modelo | Etiqueta | Total Ref | Detectadas | Valor Referencia | Valor Modelo |")
    md.append("|---|---|---|---|---|---|")
    for m, df_op in opcionales_dict.items():
        if df_op.empty:
            continue
        for _, row in df_op.iterrows():
            det_str = "Sí" if row['detectado'] else "No"
            mod_val = row['mod_valor'] if row['mod_valor'] else "-"
            md.append(f"| **{m}** | {row['etiqueta']} | 1 | {det_str} | `{row['valor']}` | `{mod_val}` |")
    md.append("\n")

    md.append("## 5. Muestra de Identificaciones Erróneas (Extras)\n")
    md.append("Primeros 10 casos por modelo de entidades extraídas por el modelo que no corresponden a ninguna referencia:\n")
    for m, df_ex in extras_dict.items():
        md.append(f"#### Modelo: **{m}** ({len(df_ex)} extras totales)")
        if not df_ex.empty:
            md.append("| Doc ID | Etiqueta Modelo | Valor Extraído |")
            md.append("|---|---|---|")
            for _, row in df_ex.head(10).iterrows():
                md.append(f"| {row['id']} | `{row['etiqueta']}` | `{row['valor']}` |")
        else:
            md.append("Sin entidades extras.")
        md.append("")
        
    md.append("## 6. Muestra de Entidades No Encontradas (Errores Comunes)\n")
    md.append("Muestra de entidades que ningún modelo o algunos modelos no lograron detectar:\n")
    
    first_model = list(resumenes_globales.keys())[0]
    if not no_enc_dict[first_model].empty:
        all_no_enc = set(no_enc_dict[first_model].apply(lambda r: (r['id'], r['etiqueta'], r['valor']), axis=1))
        for m in list(resumenes_globales.keys())[1:]:
            if not no_enc_dict[m].empty:
                s = set(no_enc_dict[m].apply(lambda r: (r['id'], r['etiqueta'], r['valor']), axis=1))
                all_no_enc = all_no_enc.intersection(s)
                
        md.append(f"**Entidades de Referencia no detectadas por NINGÚN modelo ({len(all_no_enc)} totales):**\n")
        if all_no_enc:
            md.append("| Doc ID | Etiqueta | Valor en Referencia |")
            md.append("|---|---|---|")
            for doc_id, etiq, val in list(all_no_enc)[:15]:
                md.append(f"| {doc_id} | `{etiq}` | `{val}` |")
        else:
            md.append("Todos los errores fueron capturados por al menos un modelo.")
            
    with open(reporte_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
        
    print(f"Reporte generado exitosamente en: {reporte_path}")

def parse_args():
    parser = argparse.ArgumentParser(description="Script para evaluación de métricas de modelos NER / PII.")
    
    parser.add_argument("--referencia", "-r", default=DEFAULT_REFERENCIA,
                        help="Ruta al archivo CSV de referencia supervisada.")
    parser.add_argument("--gliner2", default=DEFAULT_GLINER2,
                        help="Ruta al CSV de salida de GLiNER2.")
    parser.add_argument("--large-v25", default=DEFAULT_LARGE_V25,
                        help="Ruta al CSV de salida de Large_v25.")
    parser.add_argument("--pii-v1", default=DEFAULT_PII_V1,
                        help="Ruta al CSV de salida de PII_v1.")
    parser.add_argument("--umbral", "-u", type=int, default=85,
                        help="Umbral de similitud %% para fuzzy matching (thefuzz). Default: 85")
    parser.add_argument("--tolerancia-len", "-t", type=int, default=3,
                        help="Diferencia máxima de longitud en caracteres para fuzzy matching. Default: 3")
    parser.add_argument("--output-dir", "-o", default=DEFAULT_OUTPUT_DIR,
                        help="Directorio donde guardar el reporte, gráficos y extras.")
    parser.add_argument("--separador", "-s", default=";",
                        help="Separador de campos CSV. Default: ';'")
    
    return parser.parse_args()

def normalizar_etiquetas(df):
    if df is not None and 'etiqueta' in df.columns:
        df['etiqueta'] = df['etiqueta'].astype(str).str.lower().str.strip()
        df['etiqueta'] = df['etiqueta'].replace({'cuil': 'cuit_cuil', 'cuit': 'cuit_cuil'})
    return df

def load_csv_smart(filepath, default_sep=';'):
    df = pd.read_csv(filepath, sep=default_sep, encoding='utf-8', on_bad_lines='skip')
    if len(df.columns) == 1:
        alt_sep = ',' if default_sep == ';' else ';'
        df_alt = pd.read_csv(filepath, sep=alt_sep, encoding='utf-8', on_bad_lines='skip')
        if len(df_alt.columns) > 1:
            df = df_alt
    return normalizar_etiquetas(df)


def main():
    args = parse_args()
    
    modelos = {
        "GLiNER2": args.gliner2,
        "Large_v25": args.large_v25,
        "PII_v1": args.pii_v1,
    }
    
    output_dir = os.path.abspath(args.output_dir)
    graficos_dir = os.path.join(output_dir, "graficos")
    extras_dir = os.path.join(output_dir, "extras")
    reporte_md = os.path.join(output_dir, "reporte_metricas.md")
    
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(graficos_dir, exist_ok=True)
    os.makedirs(extras_dir, exist_ok=True)
    
    print(f"Cargando referencia desde: {args.referencia}")
    df_ref = load_csv_smart(args.referencia, default_sep=args.separador)
    
    resumenes_globales = {}
    resumenes_etiquetas = {}
    opcionales_dict = {}
    extras_dict = {}
    no_enc_dict = {}
    
    for mod_name, mod_path in modelos.items():
        print(f"Evaluando modelo: {mod_name} desde {mod_path}")
        if not os.path.exists(mod_path):
            print(f"  [ADVERTENCIA] No se encontró el archivo del modelo: {mod_path}")
            continue
            
        df_mod = load_csv_smart(mod_path, default_sep=args.separador)

        
        df_matches, df_extras, df_no_enc, df_opcionales = evaluar_modelo(
            df_ref, df_mod, umbral=args.umbral, tol_len=args.tolerancia_len
        )
        res_global, res_etiq = calcular_resumen(df_ref, df_matches, df_extras, df_no_enc)
        
        resumenes_globales[mod_name] = res_global
        resumenes_etiquetas[mod_name] = res_etiq
        opcionales_dict[mod_name] = df_opcionales
        extras_dict[mod_name] = df_extras
        no_enc_dict[mod_name] = df_no_enc
        
        # Guardar CSV de extras para cada modelo
        filename_extras = f"extras_{mod_name.lower()}.csv"
        path_extras = os.path.join(extras_dir, filename_extras)
        df_extras.to_csv(path_extras, sep=args.separador, index=False, encoding='utf-8')
        print(f"  -> {len(df_extras)} entidades extras guardadas en: {path_extras}")
        
    print("Generando gráficos...")
    generar_graficos(resumenes_globales, resumenes_etiquetas, graficos_dir)
    
    print("Generando reporte Markdown...")
    generar_reporte_markdown(
        resumenes_globales, resumenes_etiquetas, opcionales_dict, extras_dict, no_enc_dict,
        reporte_md, umbral=args.umbral, tol_len=args.tolerancia_len
    )
    
    print("\n--- RESUMEN RÁPIDO ---")
    for m, g in resumenes_globales.items():
        print(f"{m:10s} -> Precision: {g['precision']*100:6.2f}% | Recall: {g['recall']*100:6.2f}% | F1: {g['f1']*100:6.2f}%")

if __name__ == "__main__":
    main()
