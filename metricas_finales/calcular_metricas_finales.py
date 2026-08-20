import os
import sys
import argparse
import re
from datetime import datetime
import pandas as pd
import numpy as np
from rapidfuzz import fuzz
import matplotlib.pyplot as plt
from fpdf import FPDF

# --- Mapeo de Scorers de RapidFuzz ---
SCORER_MAP = {
    'partial_ratio': fuzz.partial_ratio,
    'ratio': fuzz.ratio,
    'token_sort_ratio': fuzz.token_sort_ratio,
    'token_set_ratio': fuzz.token_set_ratio,
}


def clean_val(v):
    """Limpia valores vacíos o nulos."""
    if pd.isna(v) or v is None:
        return ""
    val_str = str(v).strip()
    if val_str.lower() in ['na', 'n/a', 'none', 'nan', 'null', 'no aplica']:
        return ""
    return val_str


def normalizar_texto_persona(v):
    """Normaliza texto de persona colapsando espacios y limpiando saltos de línea."""
    val = clean_val(v)
    if not val:
        return ""
    val = re.sub(r'[\r\n\t]+', ' ', val)
    val = re.sub(r'\s+', ' ', val).strip()
    return val


def normalizar_valor_numerico(v):
    """Conserva únicamente dígitos numéricos (para DNI y CUIT/CUIL)."""
    val = clean_val(v)
    return re.sub(r'[^0-9]', '', val)


def son_etiquetas_compatibles(ref_etiq, mod_etiq):
    """Verifica compatibilidad básica de etiquetas."""
    ref = str(ref_etiq).lower().strip()
    mod = str(mod_etiq).lower().strip()

    if ref == mod:
        return True

    compat = {
        'persona': {'person', 'persona'},
        'dni': {'national_id_number', 'government_id', 'social_security_number', 'dni'},
        'cuit_cuil': {'tax_id', 'government_id', 'social_security_number', 'national_id_number', 'cuit', 'cuil', 'cuit_cuil'}
    }

    return mod in compat.get(ref, set())


def limpiar_nombre_modelo(nombre):
    """Extrae el nombre del modelo eliminando el timespan tras el último '_'."""
    base = os.path.splitext(os.path.basename(nombre))[0]
    if '_' in base:
        return base.rsplit('_', 1)[0]
    return base


def load_csv_smart(filepath, default_sep=';'):
    """Carga un CSV detectando automáticamente el separador si es necesario."""
    df = pd.read_csv(filepath, sep=default_sep, encoding='utf-8', on_bad_lines='skip')
    if len(df.columns) == 1:
        alt_sep = ',' if default_sep == ';' else ';'
        df_alt = pd.read_csv(filepath, sep=alt_sep, encoding='utf-8', on_bad_lines='skip')
        if len(df_alt.columns) > 1:
            df = df_alt

    if 'etiqueta' in df.columns:
        df['etiqueta'] = df['etiqueta'].astype(str).str.lower().str.strip()
        df['etiqueta'] = df['etiqueta'].replace({'cuil': 'cuit_cuil', 'cuit': 'cuit_cuil'})

    return df


def preparar_bd_referencia(df_ref):
    """
    Prepara la BD de referencia:
    - Persona: extrae lista de personas únicas por archivo ('id') usando 'ocr_corregido' como ground truth.
    - DNI / CUIT_CUIL: toma los registros filtrando valor válido.
    Incluye numero_archivo, span_inicio y span_fin.
    """
    ref_records = []

    # 1. Procesar Personas por documento ID
    df_persona = df_ref[df_ref['etiqueta'] == 'persona'].copy()
    for doc_id, group in df_persona.groupby('id'):
        # Tomar valores únicos de ocr_corregido
        personas_unicas = set()
        for _, row in group.iterrows():
            val = normalizar_texto_persona(row.get('ocr_corregido'))
            if not val:
                val = normalizar_texto_persona(row.get('valor'))
            if val and val not in personas_unicas:
                personas_unicas.add(val)
                ref_records.append({
                    'numero_archivo': row.get('numero_archivo'),
                    'id': doc_id,
                    'nombre_archivo': row.get('nombre_archivo'),
                    'clasificacion': row.get('clasificacion'),
                    'etiqueta': 'persona',
                    'valor': val,
                    'ocr_corregido': val,
                    'span_inicio': row.get('span_inicio'),
                    'span_fin': row.get('span_fin')
                })

    # 2. Procesar Numéricas (DNI, CUIT_CUIL)
    df_num = df_ref[df_ref['etiqueta'].isin(['dni', 'cuit_cuil'])].copy()
    for _, row in df_num.iterrows():
        val = clean_val(row.get('valor'))
        if val:
            ref_records.append({
                'numero_archivo': row.get('numero_archivo'),
                'id': row.get('id'),
                'nombre_archivo': row.get('nombre_archivo'),
                'clasificacion': row.get('clasificacion'),
                'etiqueta': row.get('etiqueta'),
                'valor': val,
                'ocr_corregido': clean_val(row.get('ocr_corregido')),
                'span_inicio': row.get('span_inicio'),
                'span_fin': row.get('span_fin')
            })

    return pd.DataFrame(ref_records)


def evaluar_canal_persona(df_ref_persona, df_mod, umbral=85, tol_len=3, scorer_name='partial_ratio', score_cutoff=0.0):
    """
    Evaluación 1 a 1 de la etiqueta 'persona' entre referencia y extracciones del modelo GLiNER.
    """
    scorer_fn = SCORER_MAP.get(scorer_name, fuzz.partial_ratio)

    matches_list = []
    extras_list = []
    no_encontradas_list = []

    all_doc_ids = sorted(list(set(df_ref_persona['id'].unique()).union(set(df_mod['id'].unique()))))

    for doc_id in all_doc_ids:
        ref_doc = df_ref_persona[df_ref_persona['id'] == doc_id].copy()
        mod_doc = df_mod[(df_mod['id'] == doc_id) & (df_mod['etiqueta'].isin(['persona', 'person']))].copy()

        ref_matched = set()
        mod_matched = set()

        ref_records = ref_doc.to_dict('records')
        mod_records = mod_doc.to_dict('records')

        # 1. Coincidencia exacta
        for r_idx, r in enumerate(ref_records):
            r_val_norm = normalizar_texto_persona(r['valor']).lower()
            if not r_val_norm:
                continue

            for m_idx, m in enumerate(mod_records):
                if m_idx in mod_matched:
                    continue
                m_val_norm = normalizar_texto_persona(m['valor']).lower()
                if not m_val_norm:
                    continue

                if r_val_norm == m_val_norm:
                    ref_matched.add(r_idx)
                    mod_matched.add(m_idx)
                    num_arch = r.get('numero_archivo') if pd.notna(r.get('numero_archivo')) else m.get('numero_archivo')
                    matches_list.append({
                        'numero_archivo': num_arch,
                        'id': doc_id,
                        'ref_etiqueta': r['etiqueta'],
                        'ref_valor': r['valor'],
                        'ref_span_inicio': r.get('span_inicio'),
                        'ref_span_fin': r.get('span_fin'),
                        'mod_etiqueta': m['etiqueta'],
                        'mod_valor': m['valor'],
                        'mod_span_inicio': m.get('span_inicio'),
                        'mod_span_fin': m.get('span_fin'),
                        'match_type': 'exacta',
                        'score': 100.0
                    })
                    break

        # 2. Coincidencia por Inclusión / Subcadena
        for r_idx, r in enumerate(ref_records):
            if r_idx in ref_matched:
                continue
            r_val_norm = normalizar_texto_persona(r['valor']).lower()
            if not r_val_norm:
                continue

            for m_idx, m in enumerate(mod_records):
                if m_idx in mod_matched:
                    continue
                m_val_norm = normalizar_texto_persona(m['valor']).lower()
                if not m_val_norm:
                    continue

                match_kind = None
                if r_val_norm in m_val_norm or m_val_norm in r_val_norm:
                    match_kind = 'inclusion'
                else:
                    r_tokens = set(r_val_norm.split())
                    m_tokens = set(m_val_norm.split())
                    if m_tokens and (m_tokens.issubset(r_tokens) or r_tokens.issubset(m_tokens)):
                        match_kind = 'inclusion'

                if match_kind:
                    ref_matched.add(r_idx)
                    mod_matched.add(m_idx)
                    num_arch = r.get('numero_archivo') if pd.notna(r.get('numero_archivo')) else m.get('numero_archivo')
                    matches_list.append({
                        'numero_archivo': num_arch,
                        'id': doc_id,
                        'ref_etiqueta': r['etiqueta'],
                        'ref_valor': r['valor'],
                        'ref_span_inicio': r.get('span_inicio'),
                        'ref_span_fin': r.get('span_fin'),
                        'mod_etiqueta': m['etiqueta'],
                        'mod_valor': m['valor'],
                        'mod_span_inicio': m.get('span_inicio'),
                        'mod_span_fin': m.get('span_fin'),
                        'match_type': match_kind,
                        'score': 100.0
                    })
                    break

        # 3. Coincidencia Fuzzy (RapidFuzz)
        for r_idx, r in enumerate(ref_records):
            if r_idx in ref_matched:
                continue
            r_val_norm = normalizar_texto_persona(r['valor']).lower()
            if not r_val_norm:
                continue

            best_m_idx = None
            best_score = 0.0
            best_m_record = None

            for m_idx, m in enumerate(mod_records):
                if m_idx in mod_matched:
                    continue
                m_val_norm = normalizar_texto_persona(m['valor']).lower()
                if not m_val_norm:
                    continue

                # Control de longitud (si no es scorer de subcadena amplia)
                if scorer_name not in ['partial_ratio', 'token_set_ratio']:
                    if abs(len(r_val_norm) - len(m_val_norm)) > tol_len:
                        continue

                score = float(scorer_fn(r_val_norm, m_val_norm, score_cutoff=score_cutoff))

                if score >= umbral and score > best_score:
                    best_score = score
                    best_m_idx = m_idx
                    best_m_record = m

            if best_m_idx is not None:
                ref_matched.add(r_idx)
                mod_matched.add(best_m_idx)
                num_arch = r.get('numero_archivo') if pd.notna(r.get('numero_archivo')) else best_m_record.get('numero_archivo')
                matches_list.append({
                    'numero_archivo': num_arch,
                    'id': doc_id,
                    'ref_etiqueta': r['etiqueta'],
                    'ref_valor': r['valor'],
                    'ref_span_inicio': r.get('span_inicio'),
                    'ref_span_fin': r.get('span_fin'),
                    'mod_etiqueta': best_m_record['etiqueta'],
                    'mod_valor': best_m_record['valor'],
                    'mod_span_inicio': best_m_record.get('span_inicio'),
                    'mod_span_fin': best_m_record.get('span_fin'),
                    'match_type': 'fuzzy',
                    'score': best_score
                })

        # No encontradas & Extras
        for r_idx, r in enumerate(ref_records):
            if r_idx not in ref_matched:
                no_encontradas_list.append({
                    'numero_archivo': r.get('numero_archivo'),
                    'id': doc_id,
                    'etiqueta': r['etiqueta'],
                    'valor': r['valor'],
                    'span_inicio': r.get('span_inicio'),
                    'span_fin': r.get('span_fin')
                })

        for m_idx, m in enumerate(mod_records):
            if m_idx not in mod_matched:
                extras_list.append({
                    'numero_archivo': m.get('numero_archivo'),
                    'id': doc_id,
                    'etiqueta': m['etiqueta'],
                    'valor': m['valor'],
                    'span_inicio': m.get('span_inicio'),
                    'span_fin': m.get('span_fin')
                })

    return pd.DataFrame(matches_list), pd.DataFrame(extras_list), pd.DataFrame(no_encontradas_list)


def evaluar_canal_numericas(df_ref_num, df_regex):
    """
    Evaluación 1 a 1 de etiquetas numéricas (dni, cuit_cuil) comparando Regex contra BD de referencia.
    Matching exacto sobre dígitos normalizados.
    """
    matches_list = []
    extras_list = []
    no_encontradas_list = []

    all_doc_ids = sorted(list(set(df_ref_num['id'].unique()).union(set(df_regex['id'].unique()))))

    for doc_id in all_doc_ids:
        ref_doc = df_ref_num[df_ref_num['id'] == doc_id].copy()
        reg_doc = df_regex[(df_regex['id'] == doc_id) & (df_regex['etiqueta'].isin(['dni', 'cuit_cuil']))].copy()

        ref_matched = set()
        reg_matched = set()

        ref_records = ref_doc.to_dict('records')
        reg_records = reg_doc.to_dict('records')

        for r_idx, r in enumerate(ref_records):
            r_num = normalizar_valor_numerico(r['valor'])
            if not r_num:
                continue

            for m_idx, m in enumerate(reg_records):
                if m_idx in reg_matched:
                    continue
                if not son_etiquetas_compatibles(r['etiqueta'], m['etiqueta']):
                    continue

                m_num = normalizar_valor_numerico(m['valor'])
                if not m_num:
                    continue

                if r_num == m_num:
                    ref_matched.add(r_idx)
                    reg_matched.add(m_idx)
                    num_arch = r.get('numero_archivo') if pd.notna(r.get('numero_archivo')) else m.get('numero_archivo')
                    matches_list.append({
                        'numero_archivo': num_arch,
                        'id': doc_id,
                        'ref_etiqueta': r['etiqueta'],
                        'ref_valor': r['valor'],
                        'ref_span_inicio': r.get('span_inicio'),
                        'ref_span_fin': r.get('span_fin'),
                        'reg_etiqueta': m['etiqueta'],
                        'reg_valor': m['valor'],
                        'reg_span_inicio': m.get('span_inicio'),
                        'reg_span_fin': m.get('span_fin'),
                        'match_type': 'exacta_numerica'
                    })
                    break

        for r_idx, r in enumerate(ref_records):
            if r_idx not in ref_matched:
                no_encontradas_list.append({
                    'numero_archivo': r.get('numero_archivo'),
                    'id': doc_id,
                    'etiqueta': r['etiqueta'],
                    'valor': r['valor'],
                    'span_inicio': r.get('span_inicio'),
                    'span_fin': r.get('span_fin')
                })

        for m_idx, m in enumerate(reg_records):
            if m_idx not in reg_matched:
                extras_list.append({
                    'numero_archivo': m.get('numero_archivo'),
                    'id': doc_id,
                    'etiqueta': m['etiqueta'],
                    'valor': m['valor'],
                    'span_inicio': m.get('span_inicio'),
                    'span_fin': m.get('span_fin')
                })

    return pd.DataFrame(matches_list), pd.DataFrame(extras_list), pd.DataFrame(no_encontradas_list)


def calcular_metricas(total_ref, n_detectadas, n_extras):
    """Calcula Precision, Recall y F1-Score."""
    precision = n_detectadas / (n_detectadas + n_extras) if (n_detectadas + n_extras) > 0 else 0.0
    recall = n_detectadas / total_ref if total_ref > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def generar_graficos(resumen_persona, resumen_num, output_dir, totales_objetivo=None):
    """Genera histogramas y gráficos comparativos de métricas."""
    graficos_dir = os.path.join(output_dir, "graficos")
    os.makedirs(graficos_dir, exist_ok=True)

    modelos = list(resumen_persona.keys())
    if not modelos:
        modelos = ["Sin Datos"]

    # 1. Histograma Persona por Modelo (Horizontal: Y=Modelos, X=Detectadas, X_max=Total Persona BD)
    fig, ax = plt.subplots(figsize=(10, max(4, len(modelos) * 0.8 + 1.5)))

    det = [resumen_persona.get(m, {}).get('detectadas', 0) for m in modelos]
    total_persona_bd = totales_objetivo.get('persona', 0) if totales_objetivo else max([resumen_persona.get(m, {}).get('total_bd', 0) for m in modelos] or [1])

    y_pos = np.arange(len(modelos))
    bars = ax.barh(y_pos, det, height=0.45, color='#2ca02c', edgecolor='black', alpha=0.85)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(modelos, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel('Cantidad de Entidades Detectadas', fontsize=11)
    ax.set_xlim(0, max(total_persona_bd, 1))
    ax.set_title(f'Evaluación por Modelo — Etiqueta Persona (Total BD = {total_persona_bd})', fontsize=12, fontweight='bold')
    if total_persona_bd > 0:
        ax.axvline(x=total_persona_bd, color='#d62728', linestyle='--', linewidth=1.5, label=f'Total Persona ({total_persona_bd})')
        ax.legend(loc='lower right')
    ax.grid(axis='x', linestyle='--', alpha=0.5)

    for bar in bars:
        w = bar.get_width()
        pct = (w / total_persona_bd * 100) if total_persona_bd > 0 else 0
        ax.annotate(f' {int(w)} ({pct:.1f}%)',
                    xy=(w, bar.get_y() + bar.get_height() / 2),
                    xytext=(3, 0), textcoords="offset points",
                    ha='left', va='center', fontsize=9, fontweight='bold')

    plt.tight_layout()
    hist_persona_path = os.path.join(graficos_dir, "histograma_persona.png")
    plt.savefig(hist_persona_path, dpi=300)
    plt.close()

    # 2. Histograma Numéricas Regex (Horizontal: Y=Etiquetas, X=% Detectadas)
    etiquetas_num = list(resumen_num.keys())
    if not etiquetas_num:
        etiquetas_num = ["dni", "cuit_cuil"]

    fig, ax = plt.subplots(figsize=(8, max(4, len(etiquetas_num) * 1.2 + 1.5)))
    y_pos_n = np.arange(len(etiquetas_num))

    pct_det_n = []
    det_n = []
    tot_n = []
    for e in etiquetas_num:
        d = resumen_num.get(e, {}).get('detectadas', 0)
        t = resumen_num.get(e, {}).get('total_bd', 0)
        pct = (d / t * 100) if t > 0 else 0.0
        pct_det_n.append(pct)
        det_n.append(d)
        tot_n.append(t)

    bars_n = ax.barh(y_pos_n, pct_det_n, height=0.4, color='#1f77b4', edgecolor='black', alpha=0.85)

    ax.set_yticks(y_pos_n)
    ax.set_yticklabels([e.upper() for e in etiquetas_num], fontsize=11, fontweight='bold')
    ax.invert_yaxis()
    ax.set_xlabel('Porcentaje de Entidades Detectadas (%)', fontsize=11)
    ax.set_xlim(0, 115)
    ax.set_title('Evaluación Extracción Regex — DNI / CUIT_CUIL (%)', fontsize=12, fontweight='bold')
    ax.grid(axis='x', linestyle='--', alpha=0.5)

    for bar, d, t in zip(bars_n, det_n, tot_n):
        w = bar.get_width()
        ax.annotate(f' {w:.1f}% ({d}/{t})',
                    xy=(w, bar.get_y() + bar.get_height() / 2),
                    xytext=(3, 0), textcoords="offset points",
                    ha='left', va='center', fontsize=9, fontweight='bold')

    plt.tight_layout()
    hist_num_path = os.path.join(graficos_dir, "histograma_numericas.png")
    plt.savefig(hist_num_path, dpi=300)
    plt.close()

    # 3. Métricas Comparativas Persona (Precision, Recall, F1)
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(modelos))
    width = 0.25

    precisions = [resumen_persona.get(m, {}).get('precision', 0) * 100 for m in modelos]
    recalls = [resumen_persona.get(m, {}).get('recall', 0) * 100 for m in modelos]
    f1s = [resumen_persona.get(m, {}).get('f1', 0) * 100 for m in modelos]

    p1 = ax.bar(x - width, precisions, width, label='Precision (%)', color='#1f77b4')
    p2 = ax.bar(x, recalls, width, label='Recall (%)', color='#aec7e8')
    p3 = ax.bar(x + width, f1s, width, label='F1-Score (%)', color='#2ca02c')

    ax.set_ylabel('Porcentaje (%)')
    ax.set_title('Métricas de Desempeño — Etiqueta Persona')
    ax.set_xticks(x)
    ax.set_xticklabels(modelos, rotation=15, ha='right')
    ax.set_ylim(0, 115)
    ax.legend()
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    for rects in [p1, p2, p3]:
        for rect in rects:
            h = rect.get_height()
            ax.annotate(f'{h:.1f}%', xy=(rect.get_x() + rect.get_width() / 2, h),
                        xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8)

    plt.tight_layout()
    metricas_comp_path = os.path.join(graficos_dir, "metricas_comparativa.png")
    plt.savefig(metricas_comp_path, dpi=300)
    plt.close()

    return hist_persona_path, hist_num_path, metricas_comp_path


def generar_pdf_reporte(resumen_obj, resumen_persona, resumen_num, img_persona, img_num, img_comp, pdf_path, args=None):
    """Genera un PDF profesional con FPDF2 conteniendo los cuadros, parámetros y gráficos."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Título principal
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Reporte de Evaluacion de Extraccion de Entidades", fill=False, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 8, f"Fecha de generacion: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", fill=False, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Parámetros de Ejecución
    if args:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "Parametros de Ejecucion:", fill=False, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_fill_color(245, 245, 245)
        ref_basename = os.path.basename(args.referencia) if hasattr(args, 'referencia') else str(args.referencia)
        params_str = (
            f"Referencia: {ref_basename}\n"
            f"Umbral Similitud: {args.umbral}  |  Tolerancia Longitud: {args.tolerancia_len}\n"
            f"Scorer: {args.scorer}  |  Score Cutoff: {args.score_cutoff}  |  Separador: '{args.separador}'"
        )
        pdf.multi_cell(0, 5, params_str, border=1, fill=True, align="L")
        pdf.ln(4)

    # 1. Cuadro con Entidades Objetivos de la BD
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "1. Entidades Objetivo de la Base de Datos Ground Truth", fill=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)

    pdf.set_fill_color(230, 230, 250)
    pdf.cell(70, 7, "Etiqueta", border=1, fill=True)
    pdf.cell(70, 7, "Total Entidades Unicas", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

    for etiq, total in resumen_obj.items():
        pdf.cell(70, 7, etiq.upper(), border=1)
        pdf.cell(70, 7, str(total), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # 2. Cuadro Conteo Persona (Modelos)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "2. Desglose de Conteos - Etiqueta Persona (Modelos GLiNER)", fill=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)

    col_w = [45, 30, 30, 30, 30]
    pdf.set_fill_color(230, 230, 250)
    pdf.cell(col_w[0], 7, "Modelo", border=1, fill=True)
    pdf.cell(col_w[1], 7, "Total BD", border=1, fill=True)
    pdf.cell(col_w[2], 7, "Detectadas", border=1, fill=True)
    pdf.cell(col_w[3], 7, "No Detectadas", border=1, fill=True)
    pdf.cell(col_w[4], 7, "Extras", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

    for mod_name, data in resumen_persona.items():
        pdf.cell(col_w[0], 7, mod_name, border=1)
        pdf.cell(col_w[1], 7, str(data['total_bd']), border=1)
        pdf.cell(col_w[2], 7, str(data['detectadas']), border=1)
        pdf.cell(col_w[3], 7, str(data['no_detectadas']), border=1)
        pdf.cell(col_w[4], 7, str(data['extras']), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # 3. Cuadro Métricas Persona
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "3. Metricas de Evaluacion - Etiqueta Persona", fill=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)

    col_w_m = [50, 35, 35, 35]
    pdf.set_fill_color(230, 230, 250)
    pdf.cell(col_w_m[0], 7, "Modelo", border=1, fill=True)
    pdf.cell(col_w_m[1], 7, "Precision (%)", border=1, fill=True)
    pdf.cell(col_w_m[2], 7, "Recall (%)", border=1, fill=True)
    pdf.cell(col_w_m[3], 7, "F1-Score (%)", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

    for mod_name, data in resumen_persona.items():
        pdf.cell(col_w_m[0], 7, mod_name, border=1)
        pdf.cell(col_w_m[1], 7, f"{data['precision']*100:.2f}%", border=1)
        pdf.cell(col_w_m[2], 7, f"{data['recall']*100:.2f}%", border=1)
        pdf.cell(col_w_m[3], 7, f"{data['f1']*100:.2f}%", border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # 4. Cuadro Conteo y Métricas Numéricas Regex
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "4. Evaluacion Extraccion Regex - DNI / CUIT_CUIL", fill=False, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)

    col_w_n = [30, 25, 25, 25, 25, 25, 25, 25]
    pdf.set_fill_color(230, 230, 250)
    pdf.cell(col_w_n[0], 7, "Etiqueta", border=1, fill=True)
    pdf.cell(col_w_n[1], 7, "Total BD", border=1, fill=True)
    pdf.cell(col_w_n[2], 7, "Detect.", border=1, fill=True)
    pdf.cell(col_w_n[3], 7, "No Det.", border=1, fill=True)
    pdf.cell(col_w_n[4], 7, "Extras", border=1, fill=True)
    pdf.cell(col_w_n[5], 7, "Prec. (%)", border=1, fill=True)
    pdf.cell(col_w_n[6], 7, "Rec. (%)", border=1, fill=True)
    pdf.cell(col_w_n[7], 7, "F1 (%)", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

    for etiq, data in resumen_num.items():
        pdf.cell(col_w_n[0], 7, etiq.upper(), border=1)
        pdf.cell(col_w_n[1], 7, str(data['total_bd']), border=1)
        pdf.cell(col_w_n[2], 7, str(data['detectadas']), border=1)
        pdf.cell(col_w_n[3], 7, str(data['no_detectadas']), border=1)
        pdf.cell(col_w_n[4], 7, str(data['extras']), border=1)
        pdf.cell(col_w_n[5], 7, f"{data['precision']*100:.2f}%", border=1)
        pdf.cell(col_w_n[6], 7, f"{data['recall']*100:.2f}%", border=1)
        pdf.cell(col_w_n[7], 7, f"{data['f1']*100:.2f}%", border=1, new_x="LMARGIN", new_y="NEXT")

    # Imprimir gráficos en el PDF
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "5. Graficos de Evaluacion", fill=False, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    if os.path.exists(img_persona):
        pdf.image(img_persona, x=15, w=180)
        pdf.ln(5)

    if os.path.exists(img_comp):
        pdf.image(img_comp, x=15, w=180)
        pdf.ln(5)

    pdf.add_page()
    if os.path.exists(img_num):
        pdf.image(img_num, x=15, w=180)

    pdf.output(pdf_path)
    print(f"Reporte PDF generado en: {pdf_path}")


def generar_markdown_reporte(resumen_obj, resumen_persona, resumen_num, md_path, args=None):
    """Genera reporte en formato Markdown."""
    lines = []
    lines.append("# Reporte Final de Evaluación de Extracción de Entidades\n")
    lines.append(f"**Fecha**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    if args:
        lines.append("### Parámetros de Ejecución")
        lines.append(f"- **Umbral RapidFuzz**: `{args.umbral}`")
        lines.append(f"- **Tolerancia Longitud**: `{args.tolerancia_len}`")
        lines.append(f"- **Scorer**: `{args.scorer}`")
        lines.append(f"- **Score Cutoff**: `{args.score_cutoff}`")
        lines.append(f"- **Separador CSV**: `{args.separador}`")
        lines.append(f"- **Referencia**: `{os.path.basename(args.referencia)}`\n")

    lines.append("## 1. Entidades Objetivo de la Base de Datos (Ground Truth)\n")
    lines.append("| Etiqueta | Total Entidades Únicas |")
    lines.append("|---|---|")
    for etiq, total in resumen_obj.items():
        lines.append(f"| **{etiq.upper()}** | {total} |")
    lines.append("\n")

    lines.append("## 2. Cuadro de Conteos — Etiqueta Persona (Modelos GLiNER)\n")
    lines.append("| Modelo | Total BD | Detectadas | No Detectadas | Extras |")
    lines.append("|---|---|---|---|---|")
    for m, d in resumen_persona.items():
        lines.append(f"| **{m}** | {d['total_bd']} | {d['detectadas']} | {d['no_detectadas']} | {d['extras']} |")
    lines.append("\n")

    lines.append("## 3. Métricas de Evaluación — Etiqueta Persona\n")
    lines.append("| Modelo | Precision (%) | Recall (%) | F1-Score (%) |")
    lines.append("|---|---|---|---|")
    for m, d in resumen_persona.items():
        lines.append(f"| **{m}** | {d['precision']*100:.2f}% | {d['recall']*100:.2f}% | {d['f1']*100:.2f}% |")
    lines.append("\n")

    lines.append("## 4. Cuadro Conteos y Métricas — Regex (DNI / CUIT_CUIL)\n")
    lines.append("| Etiqueta | Total BD | Detectadas | No Detectadas | Extras | Precision (%) | Recall (%) | F1-Score (%) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for e, d in resumen_num.items():
        lines.append(f"| **{e.upper()}** | {d['total_bd']} | {d['detectadas']} | {d['no_detectadas']} | {d['extras']} | {d['precision']*100:.2f}% | {d['recall']*100:.2f}% | {d['f1']*100:.2f}% |")
    lines.append("\n")

    lines.append("## 5. Gráficos Generados\n")
    lines.append("- `graficos/histograma_persona.png`\n")
    lines.append("- `graficos/metricas_comparativa.png`\n")
    lines.append("- `graficos/histograma_numericas.png`\n")

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"Reporte Markdown generado en: {md_path}")


def parse_args():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="Script para métricas finales de extracción de entidades (Persona y Numéricas).")
    parser.add_argument("--referencia", "-r", default=os.path.abspath(os.path.join(base_dir, "..", "bd_supervisada_conjunta_v3.csv")),
                        help="Ruta a la base de datos supervisada CSV.")
    parser.add_argument("--modelos-dir", default=os.path.join(base_dir, "extraccion_modelos"),
                        help="Carpeta con CSVs de extracciones de modelos GLiNER.")
    parser.add_argument("--regex-dir", default=os.path.join(base_dir, "extraccion_regex"),
                        help="Carpeta con CSVs de extracciones Regex.")
    parser.add_argument("--output-dir", "-o", default=os.path.join(base_dir, "output"),
                        help="Directorio de salida de los reportes.")
    parser.add_argument("--umbral", "-u", type=int, default=85,
                        help="Umbral de similitud para RapidFuzz (default: 85).")
    parser.add_argument("--tolerancia-len", "-t", type=int, default=3,
                        help="Tolerancia de longitud para RapidFuzz (default: 3).")
    parser.add_argument("--scorer", choices=list(SCORER_MAP.keys()), default="partial_ratio",
                        help="Scorer de rapidfuzz (default: partial_ratio).")
    parser.add_argument("--score-cutoff", type=float, default=0.0,
                        help="Score cutoff para rapidfuzz (default: 0.0).")
    parser.add_argument("--separador", "-s", default=";",
                        help="Separador CSV por defecto (default: ';').")
    return parser.parse_args()


def main():
    args = parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_output_dir = os.path.abspath(os.path.join(args.output_dir, f"reporte_{timestamp}"))
    os.makedirs(run_output_dir, exist_ok=True)

    ref_path = os.path.abspath(args.referencia)
    print(f"1. Cargando Base de Datos Supervisada (Referencia): {ref_path}")
    if not os.path.exists(ref_path):
        print(f"[ERROR] No existe el archivo de referencia: {ref_path}")
        sys.exit(1)

    df_ref_raw = load_csv_smart(ref_path, default_sep=args.separador)
    df_ref = preparar_bd_referencia(df_ref_raw)

    # Entidades Objetivo de la BD Ground Truth
    totales_objetivo = {
        'persona': len(df_ref[df_ref['etiqueta'] == 'persona']),
        'dni': len(df_ref[df_ref['etiqueta'] == 'dni']),
        'cuit_cuil': len(df_ref[df_ref['etiqueta'] == 'cuit_cuil'])
    }
    print(f"   Totales en BD Ground Truth -> Persona: {totales_objetivo['persona']}, DNI: {totales_objetivo['dni']}, CUIT/CUIL: {totales_objetivo['cuit_cuil']}")

    # 2. Evaluación del canal Personas (Modelos GLiNER)
    resumen_persona = {}
    df_ref_persona = df_ref[df_ref['etiqueta'] == 'persona'].copy()

    modelos_dir = os.path.abspath(args.modelos_dir)
    if os.path.exists(modelos_dir):
        csv_modelos = [os.path.join(modelos_dir, f) for f in os.listdir(modelos_dir) if f.endswith('.csv')]
    else:
        csv_modelos = []

    print(f"\n2. Evaluando Modelos GLiNER para 'persona' ({len(csv_modelos)} encontrados en {modelos_dir})...")
    for csv_file in csv_modelos:
        mod_name = limpiar_nombre_modelo(csv_file)
        print(f"   Procesando modelo: {mod_name} (archivo: {os.path.basename(csv_file)})...")
        df_mod = load_csv_smart(csv_file, default_sep=args.separador)

        df_matches, df_extras, df_no_enc = evaluar_canal_persona(
            df_ref_persona, df_mod, umbral=args.umbral, tol_len=args.tolerancia_len,
            scorer_name=args.scorer, score_cutoff=args.score_cutoff
        )

        n_det = len(df_matches)
        n_ext = len(df_extras)
        n_no_det = len(df_no_enc)
        total_bd = totales_objetivo['persona']

        prec, rec, f1 = calcular_metricas(total_bd, n_det, n_ext)

        resumen_persona[mod_name] = {
            'total_bd': total_bd,
            'detectadas': n_det,
            'no_detectadas': n_no_det,
            'extras': n_ext,
            'precision': prec,
            'recall': rec,
            'f1': f1
        }

        # Guardar CSVs
        df_matches.to_csv(os.path.join(run_output_dir, f"detectadas_persona_{mod_name}.csv"), index=False, sep=args.separador)
        df_extras.to_csv(os.path.join(run_output_dir, f"extras_persona_{mod_name}.csv"), index=False, sep=args.separador)
        df_no_enc.to_csv(os.path.join(run_output_dir, f"no_detectadas_persona_{mod_name}.csv"), index=False, sep=args.separador)

    # 3. Evaluación del canal Numéricas (Regex para DNI y CUIT_CUIL)
    resumen_num = {}
    df_ref_num = df_ref[df_ref['etiqueta'].isin(['dni', 'cuit_cuil'])].copy()

    regex_dir = os.path.abspath(args.regex_dir)
    if os.path.exists(regex_dir):
        csv_regex = [os.path.join(regex_dir, f) for f in os.listdir(regex_dir) if f.endswith('.csv')]
    else:
        csv_regex = []

    print(f"\n3. Evaluando Extracciones Regex para 'dni' y 'cuit_cuil' ({len(csv_regex)} encontrados en {regex_dir})...")
    if csv_regex:
        dfs_reg = [load_csv_smart(f, default_sep=args.separador) for f in csv_regex]
        df_regex_all = pd.concat(dfs_reg, ignore_index=True)
    else:
        df_regex_all = pd.DataFrame(columns=['id', 'etiqueta', 'valor'])

    df_matches_num, df_extras_num, df_no_enc_num = evaluar_canal_numericas(df_ref_num, df_regex_all)

    # Guardar CSVs globales numéricas
    df_matches_num.to_csv(os.path.join(run_output_dir, "detectadas_numericas_regex.csv"), index=False, sep=args.separador)
    df_extras_num.to_csv(os.path.join(run_output_dir, "extras_numericas_regex.csv"), index=False, sep=args.separador)
    df_no_enc_num.to_csv(os.path.join(run_output_dir, "no_detectadas_numericas_regex.csv"), index=False, sep=args.separador)

    for etiq in ['dni', 'cuit_cuil']:
        m_etiq = df_matches_num[df_matches_num['ref_etiqueta'] == etiq] if not df_matches_num.empty else pd.DataFrame()
        e_etiq = df_extras_num[df_extras_num['etiqueta'] == etiq] if not df_extras_num.empty else pd.DataFrame()
        n_etiq = df_no_enc_num[df_no_enc_num['etiqueta'] == etiq] if not df_no_enc_num.empty else pd.DataFrame()

        n_det = len(m_etiq)
        n_ext = len(e_etiq)
        n_no_det = len(n_etiq)
        total_bd = totales_objetivo[etiq]

        prec, rec, f1 = calcular_metricas(total_bd, n_det, n_ext)

        resumen_num[etiq] = {
            'total_bd': total_bd,
            'detectadas': n_det,
            'no_detectadas': n_no_det,
            'extras': n_ext,
            'precision': prec,
            'recall': rec,
            'f1': f1
        }

    # 4. Generación de Gráficos y Reportes
    print("\n4. Generando Gráficos y Reportes...")
    img_persona, img_num, img_comp = generar_graficos(resumen_persona, resumen_num, run_output_dir, totales_objetivo=totales_objetivo)

    md_path = os.path.join(run_output_dir, f"reporte_{timestamp}.md")
    pdf_path = os.path.join(run_output_dir, f"reporte_{timestamp}.pdf")

    generar_markdown_reporte(totales_objetivo, resumen_persona, resumen_num, md_path, args=args)
    generar_pdf_reporte(totales_objetivo, resumen_persona, resumen_num, img_persona, img_num, img_comp, pdf_path, args=args)

    print(f"\n[ÉXITO] Proceso finalizado. Resultados guardados en: {run_output_dir}")


if __name__ == "__main__":
    main()
