import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, timedelta
import os
import plotly.express as px
import plotly.graph_objects as go
import re
from fpdf import FPDF 
import io
import matplotlib.pyplot as plt
import unicodedata
import streamlit.components.v1 as components
from docxtpl import DocxTemplate
import zipfile
import extra_streamlit_components as stx

# ==============================================================================
# --- CONEXIÓN A SUPABASE (VERSIÓN SEGURA CON st.secrets) ---
# ==============================================================================
# IMPORTANTE: la URL y la key NUNCA deben escribirse directo en el código.
# Se leen desde el panel de Secrets de Streamlit Cloud (Settings > Secrets), donde
# debes tener guardado:
#
# [supabase]
# url = "https://bnypthionhjtucllbanl.supabase.co"
# key = "sb_publishable_xxxxxxxxxxxxxxxxxxxxxxxx"
#
try:
    URL_SUPABASE = st.secrets["supabase"]["url"].strip()
    KEY_SUPABASE = st.secrets["supabase"]["key"].strip()
except Exception:
    st.error("⚠️ No se encontraron las credenciales de Supabase en 'Secrets'. Configúralas en Settings > Secrets de Streamlit Cloud.")
    st.stop()

supabase: Client = create_client(URL_SUPABASE, KEY_SUPABASE)

# ==============================================================================
# --- 1. CONFIGURACIÓN INICIAL Y CONSTANTES ---
# ==============================================================================
st.set_page_config(
    page_title="Gestión de Plazos - FAE DEM Cerrillos", 
    layout="wide"
)

# Inicializar el gestor de cookies para la sesión persistente de 24 horas
cookie_manager = stx.CookieManager()

# Colores Institucionales IRIDEM
COLOR_VERDE_IRIDEM = "#A6CE39"
COLOR_GRIS_IRIDEM = "#31333F"
COLOR_GRIS_PIZARRA = "#5D6D7E"
COLOR_GRIS_FONDO = "#F8F9F9"

# Rutas de Archivos (Se mantienen nombres por compatibilidad de lógica)
SIS_HTML_FILE = "analitica_sis.html"

# Diccionario de Credenciales (Actualizado: Alan Zamora)
CREDENTIALS = {
    "admin": {"pass": "cerrillos2026", "role": "admin", "name": "Administrador"},
    "bruno.diaz": {"pass": "fae.cerrillos", "role": "user", "name": "Bruno Diaz-Casandra Mora"},
    "daniela.paula": {"pass": "fae.cerrillos", "role": "user", "name": "Daniela Izquierdo-Paula Leyton"},
    "francisca.tiare": {"pass": "fae.cerrillos", "role": "user", "name": "Francisca Salazar-Tiare Riquelme"},
    "laura.alan": {"pass": "fae.cerrillos", "role": "user", "name": "Laura Arancibia-Alan Zamora"},
    "maida.valeria": {"pass": "fae.cerrillos", "role": "user", "name": "Maida Muñoz-Valeria Orellana"},
    "marcelo.maria": {"pass": "fae.cerrillos", "role": "user", "name": "Marcelo Huento-María Constanza Correa"},
    "solange.francisco": {"pass": "fae.cerrillos", "role": "user", "name": "Solange Alegría-Francisco Carvajal"}
}

# Lista Maestra de Profesionales
PROF_BASE = sorted([
    "Bruno Diaz-Casandra Mora", 
    "Daniela Izquierdo-Paula Leyton", 
    "Francisca Salazar-Tiare Riquelme", 
    "Laura Arancibia-Alan Zamora", 
    "Maida Muñoz-Valeria Orellana", 
    "Marcelo Huento-María Constanza Correa", 
    "Solange Alegría-Francisco Carvajal"
])

# Listado Maestro de Informes para Cronogramas
NOMBRES_TABLA = [
    "Evaluación", "Avances 1", "Avances 2", "Avances 3", "Avances 4", 
    "Avances 5", "Avances 6", "Avances 7", "Avances 8", "Avances 9", 
    "Avances 10", "Avances 11", "Avances 12", "Avances 13", "Avances 14", 
    "Avances 15", "Avances 16", "Avances 17", "Avances 18", "Avances 19", "Avances 20"
]

# Columnas Extendidas de Ficha Clínica / Matriz Maestra
COLUMNAS_EXTENDIDAS = [
    "codnino", "fechanacimiento", "Nacionalidad", "CalidadJuridica", 
    "DireccionNino", "Comuna", "Tribunal", "ConQuienVive"
]

# ==============================================================================
# --- 2. INICIALIZACIÓN DE VARIABLES DE ESTADO Y COOKIES ---
# ==============================================================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# Auto-login por cookie de 24 horas
saved_user = cookie_manager.get('fae_login_cookie')
if saved_user and not st.session_state.logged_in:
    if saved_user in CREDENTIALS:
        st.session_state.logged_in = True
        st.session_state.user_role = CREDENTIALS[saved_user]["role"]
        st.session_state.user_name = CREDENTIALS[saved_user]["name"]

if 'user_role' not in st.session_state:
    st.session_state.user_role = None

if 'user_name' not in st.session_state:
    st.session_state.user_name = None

if 'caso_seleccionado' not in st.session_state:
    st.session_state.caso_seleccionado = None

if 'ver_pendientes_ind' not in st.session_state:
    st.session_state.ver_pendientes_ind = False

# ==============================================================================
# --- 3. ESTILO CSS MAESTRO (PERSONALIZACIÓN VISUAL) ---
# ==============================================================================
st.markdown(f"""
    <style>
    .stApp {{ background-color: {COLOR_GRIS_FONDO}; }}
    :root {{ --primary-color: {COLOR_VERDE_IRIDEM}; }}
    div[data-baseweb="tab-highlight"] {{ background-color: #000000 !important; }}
    button[data-baseweb="tab"][aria-selected="true"] p {{ color: #000000 !important; }}
    div[data-baseweb="select"] > div {{ background-color: {COLOR_GRIS_IRIDEM} !important; color: white !important; border-radius: 5px; }}
    div[role="listbox"] div {{ background-color: {COLOR_GRIS_IRIDEM} !important; color: white !important; }}
    .stSelectbox label {{ color: {COLOR_GRIS_IRIDEM} !important; font-weight: bold !important; }}
    
    .case-info-banner {{
        background-color: #ffffff;
        border-left: 5px solid {COLOR_VERDE_IRIDEM};
        padding: 15px;
        border-radius: 5px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 20px;
        color: {COLOR_GRIS_IRIDEM};
        font-size: 1.05rem;
        line-height: 1.6;
    }}
    .case-info-highlight {{
        background-color: #f1f9e6 !important;
        border-left: 8px solid {COLOR_VERDE_IRIDEM} !important;
        border-top: 1px solid {COLOR_VERDE_IRIDEM};
        border-right: 1px solid {COLOR_VERDE_IRIDEM};
        border-bottom: 1px solid {COLOR_VERDE_IRIDEM};
    }}
    .gray-container div[data-testid="stButton"] > button {{
        background-color: {COLOR_GRIS_PIZARRA} !important;
        color: white !important;
        border: none !important;
    }}
    .gray-container div[data-testid="stButton"] > button p {{
        color: white !important;
        font-weight: bold !important;
    }}
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# --- 4. FUNCIONES DE LOGIN ---
# ==============================================================================
def login_screen():
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(f"<h2 style='text-align: center; color: {COLOR_VERDE_IRIDEM};'>Acceso al Sistema</h2>", unsafe_allow_html=True)
            user = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            if st.button("Ingresar", use_container_width=True):
                if user in CREDENTIALS and CREDENTIALS[user]["pass"] == password:
                    st.session_state.logged_in = True
                    st.session_state.user_role = CREDENTIALS[user]["role"]
                    st.session_state.user_name = CREDENTIALS[user]["name"]
                    cookie_manager.set('fae_login_cookie', user, expires_at=datetime.now() + timedelta(days=1))
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")

if not st.session_state.logged_in:
    login_screen()
    st.stop()
    # ==============================================================================
# --- 5. FUNCIONES DE LIMPIEZA GRAMATICAL (MOTOR WORD ORIGINAL) ---
# ==============================================================================
def limpiar_y_asegurar_unicos(columnas):
    nombres_limpios = []
    for i, col in enumerate(columnas):
        texto = str(col).lower()
        texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
        texto = texto.replace(':', '').replace('/', '_').replace('.', '').replace('°', '')
        texto = re.sub(r'[^a-z0-9\s_]', '', texto)
        nuevo_nombre = "_".join(texto.split())
        if nuevo_nombre in nombres_limpios:
            nuevo_nombre = f"{nuevo_nombre}_{i}"
        nombres_limpios.append(nuevo_nombre)
    return nombres_limpios

def corregir_mayusculas(texto, es_nombre=False):
    if not isinstance(texto, str) or texto == "-":
        return texto
    texto = texto.lower().strip()
    if not texto:
        return "-"
    if es_nombre:
        return texto.title()
    return re.sub(r'(^|[.!?]\s+)(\w)', lambda m: m.group(1) + m.group(2).upper(), texto)

def limpiar_dato_word(dato, nombre_columna):
    if isinstance(dato, float) and dato.is_integer():
        dato = int(dato)
    s = str(dato).strip()
    if s in ['0', '0.0', '00:00:00', 'nan', 'NaT', 'None', '1900-01-01', '01/01/1900']:
        return "-"
    if len(s) >= 10 and re.match(r'\d{4}-\d{2}-\d{2}', s):
        try:
            return pd.to_datetime(s).strftime('%d/%m/%Y')
        except:
            return s
    es_col_nombre = any(x in nombre_columna for x in ['nombre', 'apellido', 'paterno', 'materno'])
    return corregir_mayusculas(s, es_nombre=es_col_nombre)

def extraer_objetivo_al_inicio(texto):
    texto = str(texto).strip()
    match = re.match(r'^\((.*?)\)', texto)
    if match:
        return corregir_mayusculas(match.group(1).strip())
    return "-"

def limpiar_descripcion_original(texto):
    texto = str(texto).strip()
    return re.sub(r'^\((.*?)\)', '', texto).strip()

def formatear_fecha_larga(valor):
    try:
        meses = {1:"enero", 2:"febrero", 3:"marzo", 4:"abril", 5:"mayo", 6:"junio", 7:"julio", 8:"agosto", 9:"septiembre", 10:"octubre", 11:"noviembre", 12:"diciembre"}
        dias = {0:"lunes", 1:"martes", 2:"miércoles", 3:"jueves", 4:"viernes", 5:"sábado", 6:"domingo"}
        dt = pd.to_datetime(valor, dayfirst=True)
        return f"{dias[dt.weekday()]}, {dt.day} de {meses[dt.month]} de {dt.year}"
    except:
        return valor

# ==============================================================================
# --- 6. FUNCIONES DE DATOS Y EXPORTACIÓN (SUPABASE) ---
# ==============================================================================
def normalizar_texto(texto):
    if not isinstance(texto, str):
        return ""
    texto = texto.strip().upper()
    return ''.join(c for c in unicodedata.normalize('NFKD', texto) if unicodedata.category(c) != 'Mn')

def cargar_casos():
    try:
        response = supabase.table("casos").select("*").execute()
        df = pd.DataFrame(response.data)
        if df.empty:
            return pd.DataFrame(columns=["Caso", "RIT", "Profesional", "Fecha Ingreso"] + COLUMNAS_EXTENDIDAS)
        df['Fecha Ingreso'] = pd.to_datetime(df['Fecha Ingreso']).dt.date
        df['Caso'] = df['Caso'].astype(str).str.strip()
        return df.dropna(subset=['Caso', 'Fecha Ingreso']).drop_duplicates(subset=['Caso'])
    except Exception as e:
        return pd.DataFrame(columns=["Caso", "RIT", "Profesional", "Fecha Ingreso"] + COLUMNAS_EXTENDIDAS)

def cargar_entregas():
    try:
        response = supabase.table("entregas").select("*").execute()
        df = pd.DataFrame(response.data)
        if df.empty:
            return pd.DataFrame(columns=["Caso", "Informe", "Fecha Envio Real"])
        df['Caso'] = df['Caso'].astype(str).str.strip()
        df['Fecha Envio Real'] = pd.to_datetime(df['Fecha Envio Real']).dt.date
        return df
    except Exception as e:
        return pd.DataFrame(columns=["Caso", "Informe", "Fecha Envio Real"])

def cargar_lista_espera():
    try:
        response = supabase.table("lista_espera").select("*").execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['FechaNacimiento'] = pd.to_datetime(df['FechaNacimiento'], errors='coerce').dt.date
            df['FechaIngresoLE'] = pd.to_datetime(df['FechaIngresoLE'], errors='coerce').dt.date
        return df
    except:
        return pd.DataFrame()

def convertir_a_excel_completo(df_casos_actuales, df_entregas_total):
    if df_casos_actuales.empty: return b""
    output = io.BytesIO()
    if not df_entregas_total.empty:
        df_pivot = df_entregas_total.pivot(index='Caso', columns='Informe', values='Fecha Envio Real')
    else:
        df_pivot = pd.DataFrame(columns=NOMBRES_TABLA)
    
    df_final = df_casos_actuales.merge(df_pivot, on='Caso', how='left')
    for col in NOMBRES_TABLA:
        if col not in df_final.columns: df_final[col] = None
            
    cols_base = ["codnino", "Caso", "fechanacimiento", "RIT", "Nacionalidad", "CalidadJuridica", "DireccionNino", "Comuna", "Tribunal", "ConQuienVive", "Profesional", "Fecha Ingreso"]
    cols_orden = [c for c in cols_base if c in df_final.columns] + NOMBRES_TABLA
    df_final = df_final.reindex(columns=cols_orden)
    
    for col in df_final.columns:
        if any(x in col for x in ["Fecha", "fechanacimiento"]) or col in NOMBRES_TABLA:
            df_final[col] = pd.to_datetime(df_final[col], errors='coerce').dt.strftime('%d-%m-%Y').replace("NaT", "")
            
    df_final.insert(0, "N°", range(1, len(df_final) + 1))
    if "Fecha Ingreso" in df_final.columns:
        df_final = df_final.rename(columns={"Fecha Ingreso": "Fecha de Ingreso"})
        
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Listado_Completo')
    return output.getvalue()

def convertir_a_excel_simple(df):
    output = io.BytesIO()
    df_simple = df[["#", "Caso", "Profesional", "Fecha Ingreso", "RIT"]].copy()
    df_simple['Fecha Ingreso'] = pd.to_datetime(df_simple['Fecha Ingreso']).dt.strftime('%d-%m-%Y')
    df_simple = df_simple.rename(columns={"#": "N°", "Fecha Ingreso": "Fecha de Ingreso"})
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_simple.to_excel(writer, index=False, sheet_name='Nomina_FAE')
    return output.getvalue()

# ==============================================================================
# --- 7. FUNCIONES PDF ---
# ==============================================================================
def generar_pdf_visual(prof_nombre, df_resumen, data_grafico_barras, cumple_count, no_cumple_count):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(213, 219, 219); pdf.rect(0, 0, 210, 45, 'F')
    pdf.set_text_color(49, 51, 63); pdf.set_font("helvetica", "B", 18)
    pdf.cell(0, 15, "CONTROL DE PLAZOS Y CUMPLIMIENTO DE ENTREGAS", ln=True, align="C")
    pdf.set_font("helvetica", "B", 14); pdf.set_text_color(120, 150, 40)
    pdf.cell(0, 10, "FAE DEM CERRILLOS", ln=True, align="C")
    pdf.set_text_color(49, 51, 63); pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 10, f"Profesional: {prof_nombre} | Generado: {datetime.now().strftime('%d-%m-%Y')}", ln=True, align="C")
    pdf.ln(15)
    try:
        plt.figure(figsize=(10, 5))
        df_bar = pd.DataFrame(data_grafico_barras)
        plt.bar(df_bar['Caso'], df_bar['Días'], color=[COLOR_VERDE_IRIDEM if t == "Días desde último envío" else COLOR_GRIS_IRIDEM for t in df_bar['Tipo']])
        plt.axhline(y=90, color='#ff7f7f', linestyle='-')
        plt.xticks(rotation=45, ha='right', fontsize=8); plt.tight_layout()
        img_buf = io.BytesIO(); plt.savefig(img_buf, format='png'); plt.close()
        pdf.image(img_buf, x=10, w=190)
    except: pass
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16); pdf.set_text_color(93, 109, 126)
    pdf.cell(0, 15, "RESUMEN DE PROXIMAS ENTREGAS", ln=True)
    anchos = [45, 22, 22, 28, 25, 30, 18] 
    titulos = ["Caso", "Prox. Inf.", "F. Limite", "Est. (Ingreso)", "Venc. (3m)", "Est. (Operativo)", "Meses"]
    pdf.set_font("helvetica", "B", 8); pdf.set_fill_color(213, 219, 219); pdf.set_text_color(0, 0, 0)
    for i, t in enumerate(titulos): pdf.cell(anchos[i], 10, t, border=1, fill=True, align="C")
    pdf.ln(); pdf.set_font("helvetica", "", 7)
    for _, row in df_resumen.iterrows():
            # Limpieza profunda de emojis para evitar errores en la nube
            caso_limpio = "".join(c for c in str(row['Caso']) if ord(c) < 128)[:28]
            est_ingreso = str(row['Estado (Ingreso)']).replace("🔴","").replace("🟠","").replace("⚪","").strip()
            est_operativo = str(row['Estado (Operativo)']).replace("🔴","").replace("🟢","").strip()
            
            pdf.cell(anchos[0], 8, caso_limpio, border=1)
            pdf.cell(anchos[1], 8, str(row['Próximo Informe']), border=1, align="C")
            pdf.cell(anchos[2], 8, str(row['F. Límite (Teo)']), border=1, align="C")
            pdf.cell(anchos[3], 8, est_ingreso, border=1, align="C")
            pdf.cell(anchos[4], 8, str(row['Venc. (3m)']), border=1, align="C")
            pdf.cell(anchos[5], 8, est_operativo, border=1, align="C")
            pdf.cell(anchos[6], 8, str(row['Meses']), border=1, align="C")
            pdf.ln()
    return bytes(pdf.output())

def generar_pdf_cronograma(caso_nombre, f_ingreso, df_hitos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(213, 219, 219); pdf.rect(0, 0, 210, 40, 'F')
    pdf.set_font("helvetica", "B", 16); pdf.cell(0, 10, "CRONOGRAMA COMPLETO DE INFORMES", ln=True, align="C")
    pdf.set_font("helvetica", "", 11); pdf.cell(0, 8, f"Caso: {caso_nombre}", ln=True, align="C")
    pdf.ln(15); pdf.set_font("helvetica", "B", 8); pdf.set_fill_color(49, 51, 63); pdf.set_text_color(255, 255, 255)
    anchos = [30, 30, 30, 45, 35, 25]
    headers = ["Informe", "F. Limite", "F. Envio", "Desfase", "F. Corresp.", "Vigencia"]
    for i, h in enumerate(headers): pdf.cell(anchos[i], 10, h, border=1, fill=True, align="C")
    pdf.ln(); pdf.set_text_color(0, 0, 0); pdf.set_font("helvetica", "", 7)
    for _, row in df_hitos.iterrows():
        # Limpieza de emojis/caracteres especiales: helvetica no los soporta y rompe el PDF
        desf_limpio = "".join(c for c in str(row['Desfase']) if ord(c) < 128).strip()[:30]
        vig_limpio = "".join(c for c in str(row['Vigencia (3m)']) if ord(c) < 128).strip()
        pdf.cell(anchos[0], 8, str(row['Informe']), border=1, align="C")
        pdf.cell(anchos[1], 8, str(row['Fecha Límite']), border=1, align="C")
        pdf.cell(anchos[2], 8, str(row['Fecha Envío Real']), border=1, align="C")
        pdf.cell(anchos[3], 8, desf_limpio, border=1, align="C")
        pdf.cell(anchos[4], 8, str(row['Fecha Corresponde']), border=1, align="C")
        pdf.cell(anchos[5], 8, vig_limpio, border=1, align="C")
        pdf.ln()
    return bytes(pdf.output())
    # ==============================================================================
# --- 8. BARRA LATERAL (GESTIÓN NUBE) ---
# ==============================================================================
if st.session_state.user_role == "admin":
    st.sidebar.header("1. Registrar Nuevo Caso")
    with st.sidebar.form("nuevo_caso", clear_on_submit=True):
        n_caso = st.text_input("Nombre del Caso")
        n_rit = st.text_input("Causa RIT")
        n_codnino = st.text_input("Cod. Niño")
        n_fecnac = st.date_input("Fecha de Nacimiento", datetime.now(), min_value=datetime(1990, 1, 1))
        prof = st.selectbox("Profesional", PROF_BASE)
        f_ing = st.date_input("Fecha Ingreso", datetime.now())
        if st.form_submit_button("Guardar Caso") and n_caso:
            try:
                nuevo = {
                    "Caso": str(n_caso).strip(), 
                    "RIT": str(n_rit).strip(), 
                    "codnino": str(n_codnino).strip(),
                    "fechanacimiento": str(n_fecnac),
                    "Profesional": prof, 
                    "Fecha Ingreso": str(f_ing)
                }
                supabase.table("casos").insert(nuevo).execute()
                st.sidebar.success(f"✅ Caso {n_caso} guardado en la nube")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"❌ Error al guardar: {e}")

    st.sidebar.divider()
    st.sidebar.header("2. Carga Masiva (Matriz Maestra)")
    archivo_excel = st.sidebar.file_uploader("Subir Matriz de Carga", type=["xlsx"], key="carga_masiva")
    modo_reinicio = st.sidebar.checkbox("🚨 MODO REINICIO: Borrar base actual y cargar desde cero")
    
    if archivo_excel:
        try:
            df_excel = pd.read_excel(archivo_excel)
            df_excel.columns = [str(c).strip() for c in df_excel.columns]
            cols_norm = {c.lower(): c for c in df_excel.columns}
            
            c_caso = cols_norm.get("caso")
            c_prof = cols_norm.get("profesional")
            c_rit = cols_norm.get("rit")
            c_fecha = cols_norm.get("fecha ingreso") or cols_norm.get("fecha de ingreso")
            
            c_codnino = cols_norm.get("codnino")
            c_nacimiento = cols_norm.get("fechanacimiento")
            c_nacionalidad = cols_norm.get("nacionalidad")
            c_calidad = cols_norm.get("calidadjuridica")
            c_direccion = cols_norm.get("direccionnino")
            c_comuna = cols_norm.get("comuna")
            c_tribunal = cols_norm.get("tribunal")
            c_convive = cols_norm.get("conquienvive")
            
            if c_caso and c_prof and c_fecha:
                if st.sidebar.button("🚀 Sincronizar Matriz Completa"):
                    barra_progreso = st.sidebar.progress(0)
                    if modo_reinicio:
                        supabase.table("entregas").delete().neq("id", 0).execute()
                        supabase.table("casos").delete().neq("id", 0).execute()
                    
                    total_filas = len(df_excel)
                    for i, (_, row) in enumerate(df_excel.iterrows()):
                        nombre_c = str(row[c_caso]).strip()
                        f_ing_dt = pd.to_datetime(row[c_fecha], errors='coerce', dayfirst=True)
                        f_ing_val = f_ing_dt.strftime('%Y-%m-%d') if pd.notnull(f_ing_dt) else None
                        
                        if f_ing_val:
                            meta_vals = {
                                "Caso": nombre_c, "RIT": str(row[c_rit]).strip() if c_rit else "S/R",
                                "Profesional": str(row[c_prof]).strip(), "Fecha Ingreso": f_ing_val,
                                "codnino": str(row[c_codnino]).strip() if c_codnino else "S/I",
                                "fechanacimiento": str(row[c_nacimiento]).strip() if c_nacimiento else "S/I",
                                "Nacionalidad": str(row[c_nacionalidad]).strip() if c_nacionalidad else "S/I",
                                "CalidadJuridica": str(row[c_calidad]).strip() if c_calidad else "S/I",
                                "DireccionNino": str(row[c_direccion]).strip() if c_direccion else "S/I",
                                "Comuna": str(row[c_comuna]).strip() if c_comuna else "S/I",
                                "Tribunal": str(row[c_tribunal]).strip() if c_tribunal else "S/I",
                                "ConQuienVive": str(row[c_convive]).strip() if c_convive else "S/I"
                            }
                            supabase.table("casos").upsert(meta_vals, on_conflict="Caso").execute()
                            
                            for inf in NOMBRES_TABLA:
                                col_inf = cols_norm.get(inf.lower())
                                if col_inf and pd.notnull(row[col_inf]):
                                    f_env_dt = pd.to_datetime(row[col_inf], errors='coerce', dayfirst=True)
                                    if pd.notnull(f_env_dt):
                                        envio = {"Caso": nombre_c, "Informe": inf, "Fecha Envio Real": f_env_dt.strftime('%Y-%m-%d')}
                                        supabase.table("entregas").upsert(envio, on_conflict="Caso, Informe").execute()
                        barra_progreso.progress((i + 1) / total_filas)
                    st.sidebar.success("✅ ¡Sincronización Exitosa!")
                    st.rerun()
        except Exception as e: 
            st.sidebar.error(f"Error: {e}")

# df_casos_sidebar se sigue calculando siempre porque se reutiliza más abajo
# (sección "4. Eliminar Caso"), pero el formulario de registro de envío
# solo se muestra si el usuario es admin.
df_casos_sidebar = cargar_casos()
if st.session_state.user_role != "admin":
    df_casos_sidebar = df_casos_sidebar[df_casos_sidebar['Profesional'] == st.session_state.user_name]

if st.session_state.user_role == "admin":
    st.sidebar.divider()
    st.sidebar.header("3. Registrar Envío")
    if not df_casos_sidebar.empty:
        with st.sidebar.form("registrar_envio", clear_on_submit=True):
            caso_envio = st.selectbox("Selecciona el Caso", sorted(df_casos_sidebar['Caso'].unique()))
            informe_envio = st.selectbox("¿Qué informe envió?", NOMBRES_TABLA)
            f_envio = st.date_input("Fecha Real de Envío", datetime.now())
            if st.form_submit_button("Registrar Envío"):
                try:
                    nuevo_e = {"Caso": caso_envio, "Informe": informe_envio, "Fecha Envio Real": str(f_envio)}
                    supabase.table("entregas").upsert(nuevo_e, on_conflict="Caso, Informe").execute()
                    st.sidebar.success("✅ Envío registrado en la nube")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"❌ Error: {e}")

if st.session_state.user_role == "admin":
    st.sidebar.divider()
    st.sidebar.header("4. 🗑️ Eliminar Caso")
    if not df_casos_sidebar.empty:
        lista_borrar = sorted(df_casos_sidebar['Caso'].unique())
        caso_a_borrar = st.sidebar.selectbox("Caso a eliminar", ["---"] + lista_borrar)
        if st.sidebar.button("Eliminar permanentemente"):
            if caso_a_borrar != "---":
                try:
                    supabase.table("casos").delete().eq("Caso", caso_a_borrar).execute()
                    st.sidebar.warning(f"Caso '{caso_a_borrar}' eliminado de la nube.")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Error al eliminar: {e}")

    st.sidebar.divider()
    st.sidebar.header("5. 🛠️ Gestión y Corrección")
    
    with st.sidebar.expander("📝 Editar Información del Caso"):
        if not df_casos_sidebar.empty:
            caso_a_editar = st.selectbox("Selecciona caso para editar", ["---"] + sorted(df_casos_sidebar['Caso'].unique()))
            if caso_a_editar != "---":
                datos_actuales = df_casos_sidebar[df_casos_sidebar['Caso'] == caso_a_editar].iloc[0]
                with st.form("form_unificado_editar"):
                    nuevo_nombre_c = st.text_input("Nombre del Caso", caso_a_editar)
                    nuevo_rit = st.text_input("Causa RIT", datos_actuales['RIT'])
                    nuevo_prof = st.selectbox("Profesional", PROF_BASE, index=PROF_BASE.index(datos_actuales['Profesional']) if datos_actuales['Profesional'] in PROF_BASE else 0)
                    nueva_fecha_ing = st.date_input("Fecha Ingreso", datos_actuales['Fecha Ingreso'])
                    
                    if st.form_submit_button("Guardar Cambios"):
                        try:
                            datos_nuevos = {"Caso": nuevo_nombre_c.strip(), "RIT": nuevo_rit, "Profesional": nuevo_prof, "Fecha Ingreso": str(nueva_fecha_ing)}
                            supabase.table("casos").update(datos_nuevos).eq("Caso", caso_a_editar).execute()
                            st.success("Información actualizada en la nube.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")

    with st.sidebar.expander("📅 Corregir/Eliminar Fecha de Informe"):
        df_e_corr = cargar_entregas()
        if not df_e_corr.empty:
            caso_f_corr = st.selectbox("Selecciona Caso", sorted(df_e_corr['Caso'].unique()), key="corr_f_c")
            informes_enviados = df_e_corr[df_e_corr['Caso'] == caso_f_corr]['Informe'].unique()
            inf_a_corr = st.selectbox("Informe a gestionar", informes_enviados)
            fecha_actual = df_e_corr[(df_e_corr['Caso'] == caso_f_corr) & (df_e_corr['Informe'] == inf_a_corr)]['Fecha Envio Real'].iloc[0]
            nueva_f_corr = st.date_input("Nueva Fecha Real", fecha_actual)
            
            c_upd, c_del = st.columns(2)
            with c_upd:
                if st.button("Actualizar Fecha"):
                    try:
                        supabase.table("entregas").update({"Fecha Envio Real": str(nueva_f_corr)}).match({"Caso": caso_f_corr, "Informe": inf_a_corr}).execute()
                        st.success("Fecha actualizada.")
                        st.rerun()
                    except Exception as e: st.error(f"Error: {e}")
            with c_del:
                if st.button("🗑️ Eliminar Informe"):
                    try:
                        supabase.table("entregas").delete().match({"Caso": caso_f_corr, "Informe": inf_a_corr}).execute()
                        st.warning("Registro eliminado.")
                        st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    st.sidebar.divider()
    st.sidebar.header("6. ⏳ Cargar Lista de Espera")
    archivo_espera = st.sidebar.file_uploader("Subir Excel Lista Espera", type=["xlsx"])
    if archivo_espera:
        try:
            df_espera_raw = pd.read_excel(archivo_espera)
            # Solo se envían las columnas que existen en la tabla 'lista_espera' de Supabase.
            # Cualquier columna extra del Excel (ej. "CausalIngreso") se ignora para no romper la carga.
            cols_interes = ["Nombres", "Apellido_Paterno", "Apellido_Materno", "FechaNacimiento", "Rut", "FechaIngresoLE", "Tribunal", "RIT", "FechaOrden", "ComunaNiño_a"]
            cols_presentes = [c for c in cols_interes if c in df_espera_raw.columns]
            cols_faltantes = [c for c in cols_interes if c not in df_espera_raw.columns]
            cols_ignoradas = [c for c in df_espera_raw.columns if c not in cols_interes]
            df_espera_filtrado = df_espera_raw[cols_presentes].copy()
            if cols_faltantes:
                st.sidebar.warning(f"⚠️ Columnas no encontradas en el Excel (se omiten): {', '.join(cols_faltantes)}")
            if cols_ignoradas:
                st.sidebar.info(f"ℹ️ Columnas del Excel no usadas por el sistema: {', '.join(cols_ignoradas)}")
            if st.sidebar.button("🔄 Actualizar Lista de Espera"):
                supabase.table("lista_espera").delete().neq("id", 0).execute()
                registros = df_espera_filtrado.to_dict(orient="records")
                for r in registros:
                    for k, v in r.items():
                        if "Fecha" in k and pd.notnull(v): r[k] = str(pd.to_datetime(v).date())
                        elif pd.isnull(v): r[k] = None
                supabase.table("lista_espera").insert(registros).execute()
                st.sidebar.success("Lista de espera actualizada en la nube.")
                st.rerun()
        except Exception as e: 
            st.sidebar.error(f"Error: {e}")

st.sidebar.divider()
if st.sidebar.button("🚪 Cerrar Sesión"):
    cookie_manager.delete('fae_login_cookie')
    st.session_state.logged_in = False
    st.rerun()
    # ==============================================================================
# --- 9. CUERPO PRINCIPAL ---
# ==============================================================================
df_c = cargar_casos()
df_e = cargar_entregas()

if not df_c.empty:
    hoy = datetime.now().date()
    
    st.markdown("<h1 style='text-align: center; color: black; margin-bottom: 0;'>Ecosistema Digital FAE DEM Cerrillos</h1>", unsafe_allow_html=True)
    st.markdown(f"<h3 style='text-align: center; color: {COLOR_GRIS_PIZARRA}; margin-top: 0;'>Control de Plazos y Automatización Institucional</h3>", unsafe_allow_html=True)
    st.divider()

    if st.session_state.user_role == "admin":
        tab_ind, tab_global, tab_espera, tab_sis, tab_word = st.tabs(["👤 Vista por Profesional", "🌎 Panel Global", "⏳ Lista de Espera", "📊 Analítica SIS", "📝 Automatizador Word"])
    else:
        tab_ind, tab_word = st.tabs(["👤 Mi Vista Profesional", "📝 Automatizador Word"])

    # --- TAB 1: VISTA POR PROFESIONAL ---
    with tab_ind:
        st.subheader("🔍 Consulta por Profesional")
        if st.session_state.user_role == "admin":
            lista_profs_f = sorted(df_c['Profesional'].unique())
            prof_sel = st.selectbox("Selecciona Profesional:", lista_profs_f, key="prof_sel_ind")
        else:
            prof_sel = st.session_state.user_name
            st.info(f"Visualizando casos de: **{prof_sel}**")
            
        df_c_filtrado = df_c[df_c['Profesional'] == prof_sel]

        if not df_c_filtrado.empty:
            col_graf1, col_graf2 = st.columns([5, 1])
            data_grafico_barras = [] 
            detalles_pendientes_ind = []
            with col_graf1:
                st.markdown("#### 📊 Días desde último envío por caso")
                for c in df_c_filtrado['Caso'].unique():
                    envios_caso = df_e[df_e['Caso'] == c]
                    f_ingreso_c = df_c[df_c['Caso'] == c].iloc[0]['Fecha Ingreso']
                    meses_ant = (hoy.year - f_ingreso_c.year) * 12 + (hoy.month - f_ingreso_c.month)
                    if hoy.day < f_ingreso_c.day: meses_ant -= 1
                    
                    if not envios_caso.empty:
                        ultima_fecha = pd.to_datetime(envios_caso['Fecha Envio Real']).max().date()
                        etiqueta = "Días desde último envío"
                    else:
                        ultima_fecha = f_ingreso_c
                        etiqueta = "días desde ingreso (Diagnóstico)"
                    
                    vencimiento_3m = (pd.to_datetime(ultima_fecha) + pd.DateOffset(months=3)).date()
                    
                    data_grafico_barras.append({
                        "Caso": c, "Días": (hoy - ultima_fecha).days, "Tipo": etiqueta, 
                        "Fecha Referencia": ultima_fecha.strftime('%d-%m-%Y'), 
                        "Meses en Programa": f"{meses_ant} meses",
                        "Límite 3 meses": vencimiento_3m.strftime('%d-%m-%Y')
                    })

                    # --- Detalle de casos fuera de plazo (más de 3 meses desde último envío) ---
                    if (hoy - ultima_fecha).days > 90:
                        entregados_lista = envios_caso['Informe'].tolist()
                        idx_proximo = max([NOMBRES_TABLA.index(inf) for inf in entregados_lista if inf in NOMBRES_TABLA]) + 1 if entregados_lista else 0
                        proximo_inf = NOMBRES_TABLA[idx_proximo] if idx_proximo < len(NOMBRES_TABLA) else "-"
                        detalles_pendientes_ind.append({
                            "Caso": c,
                            "RIT": df_c[df_c['Caso'] == c].iloc[0]['RIT'],
                            "Próximo Informe": proximo_inf,
                            "Venc. (3m)": vencimiento_3m.strftime('%d-%m-%Y'),
                            "Meses": meses_ant
                        })
                
                df_grafico = pd.DataFrame(data_grafico_barras)
                # Etiqueta de texto sobre cada barra: marca especial cuando lleva 0 días
                df_grafico['Etiqueta'] = df_grafico['Días'].apply(lambda d: "🆕 0 (Recién ingresado)" if d == 0 else str(d))
                fig_barras = px.bar(df_grafico, x='Caso', y='Días', color='Tipo', text='Etiqueta', 
                                   hover_name=None,
                                   hover_data={
                                       'Caso': False,
                                       'Tipo': False,
                                       'Días': False,
                                       'Etiqueta': False,
                                       'Fecha Referencia': True,
                                       'Meses en Programa': True,
                                       'Límite 3 meses': True
                                   },
                                   color_discrete_map={"Días desde último envío": COLOR_VERDE_IRIDEM, "días desde ingreso (Diagnóstico)": COLOR_GRIS_IRIDEM})
                fig_barras.add_hline(y=90, line_color="#ff7f7f", line_width=2)
                fig_barras.update_layout(xaxis_tickangle=-45, height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                evento_clic = st.plotly_chart(fig_barras, use_container_width=True, on_select="rerun", key="grafico_barras_ind")
                if evento_clic and evento_clic.selection and len(evento_clic.selection.points) > 0:
                    st.session_state.caso_seleccionado = evento_clic.selection.points[0]['x']

            cumple_count = sum(1 for d in data_grafico_barras if d['Días'] <= 90)
            no_cumple_count = len(data_grafico_barras) - cumple_count

            with col_graf2:
                st.markdown("#### 🎯 Cumplimiento")
                fig_torta = go.Figure(data=[go.Pie(
                    labels=['Al día', 'Fuera de plazo'], 
                    values=[cumple_count, no_cumple_count], 
                    hole=.5, 
                    marker_colors=[COLOR_VERDE_IRIDEM, COLOR_GRIS_IRIDEM],
                    textposition='inside',
                    insidetextorientation='horizontal',
                    textinfo='percent',
                    textfont=dict(size=14, color="white")
                )])
                fig_torta.update_layout(
                    margin=dict(t=0, b=0, l=0, r=0), 
                    height=300, 
                    showlegend=True, 
                    legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
                    paper_bgcolor='rgba(0,0,0,0)'
                )
                st.plotly_chart(fig_torta, use_container_width=True)
                st.write(f"<div style='margin-top: 10px; text-align: center;'><b>Total: {cumple_count + no_cumple_count} casos</b></div>", unsafe_allow_html=True)

                if no_cumple_count > 0:
                    st.markdown('<div class="gray-container">', unsafe_allow_html=True)
                    if st.button(f"⚠️ Ver {no_cumple_count} Informes Pendientes", use_container_width=True, key="btn_pendientes_ind"):
                        st.session_state.ver_pendientes_ind = not st.session_state.ver_pendientes_ind
                    st.markdown('</div>', unsafe_allow_html=True)

            if st.session_state.ver_pendientes_ind and no_cumple_count > 0:
                st.warning(f"⚠️ Casos Fuera de Plazo: {prof_sel}")
                st.dataframe(pd.DataFrame(detalles_pendientes_ind), use_container_width=True, hide_index=True)

            st.divider()
            lista_casos_f = sorted(df_c_filtrado['Caso'].unique())
            if st.session_state.caso_seleccionado not in lista_casos_f:
                st.session_state.caso_seleccionado = lista_casos_f[0]
            lista_con_marca = [f"📍 {c}" if c == st.session_state.caso_seleccionado else c for c in lista_casos_f]
            idx_sel = lista_casos_f.index(st.session_state.caso_seleccionado)
            caso_sel_raw = st.selectbox("2. Caso seleccionado:", lista_con_marca, index=idx_sel)
            caso_sel = caso_sel_raw.replace("📍 ", "")
            st.session_state.caso_seleccionado = caso_sel
            datos_c = df_c[df_c['Caso'] == caso_sel].iloc[0]
            f_ingreso = datos_c['Fecha Ingreso']
            m_ant_tit = (hoy.year - f_ingreso.year) * 12 + (hoy.month - f_ingreso.month)
            if hoy.day < f_ingreso.day: m_ant_tit -= 1

            try:
                f_nac_sel = pd.to_datetime(datos_c.get('fechanacimiento'), errors='coerce')
                edad_sel = hoy.year - f_nac_sel.year - ((hoy.month, hoy.day) < (f_nac_sel.month, f_nac_sel.day)) if pd.notnull(f_nac_sel) else "S/I"
            except:
                edad_sel = "S/I"
            edad_sel_txt = f"{edad_sel} años" if edad_sel != "S/I" else "S/I"
            
            st.markdown(f"""<div class="case-info-banner"><b>Caso:</b> {caso_sel} | <b>RIT:</b> {datos_c['RIT']} | <b>Edad:</b> {edad_sel_txt} | <b>Ingreso:</b> {f_ingreso.strftime('%d-%m-%Y')} | <b>Antigüedad:</b> {m_ant_tit} meses</div>""", unsafe_allow_html=True)

            hitos_inicial, hitos_larga = [], []
            for i, nombre_inf in enumerate(NOMBRES_TABLA):
                fecha_limite = (pd.to_datetime(f_ingreso) + pd.DateOffset(months=3 * (i + 1))).date()
                reg_e = df_e[(df_e['Caso'] == caso_sel) & (df_e['Informe'] == nombre_inf)]
                f_envio_str = reg_e.iloc[0]['Fecha Envio Real'].strftime('%d-%m-%Y') if not reg_e.empty else "-"
                
                if i == 0: f_ref_ope = f_ingreso
                else:
                    reg_prev = df_e[(df_e['Caso'] == caso_sel) & (df_e['Informe'] == NOMBRES_TABLA[i-1])]
                    f_ref_ope = reg_prev.iloc[0]['Fecha Envio Real'] if not reg_prev.empty else None
                
                venc_ope_str = (pd.to_datetime(f_ref_ope) + pd.DateOffset(months=3)).strftime('%d-%m-%Y') if f_ref_ope else "-"
                vigencia_str = "🟢 VIGENTE" if f_ref_ope and hoy <= (pd.to_datetime(f_ref_ope) + pd.DateOffset(months=3)).date() else "🔴 VENCIDO"

                # --- CÁLCULO DE DESFASE (FIX: esta clave faltaba y rompía el PDF del cronograma) ---
                if not reg_e.empty:
                    f_real = reg_e.iloc[0]['Fecha Envio Real']
                    desfase_dias = (f_real - fecha_limite).days
                    desfase_str = f"✅ A tiempo ({abs(desfase_dias)} días)" if desfase_dias <= 0 else f"⚠️ Retraso de {desfase_dias} días"
                else:
                    dias_res = (fecha_limite - hoy).days
                    desfase_str = f"Atrasado por {abs(dias_res)} días" if dias_res < 0 else f"Faltan {dias_res} días"
                
                fila = {
                    "Informe": nombre_inf, 
                    "Fecha Límite": fecha_limite.strftime('%d-%m-%Y'), 
                    "Fecha Envío Real": f_envio_str, 
                    "Desfase": desfase_str, 
                    "Fecha Corresponde": venc_ope_str, 
                    "Vigencia (3m)": vigencia_str
                }
                if i < 7: hitos_inicial.append(fila)
                else: hitos_larga.append(fila)

            st.write("### ⏱️ Cronograma de Informes")
            if caso_sel:
                try:
                    pdf_cron = generar_pdf_cronograma(caso_sel, f_ingreso, pd.DataFrame(hitos_inicial + hitos_larga))
                    st.download_button("📥 Descargar Cronograma (PDF)", pdf_cron, f"Cronograma_{caso_sel}.pdf")
                except Exception as e:
                    st.warning(f"Error al generar PDF: {e}")
            
            st.dataframe(pd.DataFrame(hitos_inicial), use_container_width=True, hide_index=True)
            if hitos_larga:
                st.markdown("---")
                st.write("### 🏠 Larga Permanencia")
                st.dataframe(pd.DataFrame(hitos_larga), use_container_width=True, hide_index=True)

            # --- CUADROS A Y B ---
            st.divider()
            resumen_maestro_pdf = [] 
            for _, row in df_c_filtrado.iterrows():
                c_nombre, f_ing = row['Caso'], row['Fecha Ingreso']
                entregas_caso = df_e[df_e['Caso'] == c_nombre]
                idx_proximo = len(entregas_caso)
                if idx_proximo < len(NOMBRES_TABLA):
                    proximo_inf = NOMBRES_TABLA[idx_proximo]
                    f_ref_op = pd.to_datetime(entregas_caso['Fecha Envio Real']).max().date() if not entregas_caso.empty else f_ing
                    venc_op = (pd.to_datetime(f_ref_op) + pd.DateOffset(months=3)).date()
                    fecha_limite_teo = (pd.to_datetime(f_ing) + pd.DateOffset(months=3 * (idx_proximo + 1))).date()
                    resumen_maestro_pdf.append({
                        "Caso": c_nombre, "Próximo Informe": proximo_inf, "F. Límite (Teo)": fecha_limite_teo.strftime('%d-%m-%Y'), 
                        "Estado (Ingreso)": "🔴 VENCIDO" if hoy > fecha_limite_teo else "⚪ EN PLAZO", 
                        "Venc. (3m)": venc_op.strftime('%d-%m-%Y'), "Estado (Operativo)": "🟢 VIGENTE" if hoy <= venc_op else "🔴 VENCIDO", "Meses": "0"
                    })
            
            df_maestro_vista = pd.DataFrame(resumen_maestro_pdf)
            if not df_maestro_vista.empty:
                st.subheader("📋 Próximas Entregas")
                st.dataframe(df_maestro_vista[["Caso", "Próximo Informe", "Venc. (3m)", "Estado (Operativo)"]], use_container_width=True, hide_index=True)
                try:
                    pdf_ejecutivo = generar_pdf_visual(prof_sel, df_maestro_vista, data_grafico_barras, cumple_count, no_cumple_count)
                    st.download_button("📥 Descargar Reporte Ejecutivo (PDF)", pdf_ejecutivo, f"Reporte_{prof_sel}.pdf")
                except Exception as e:
                    st.info(f"Reporte PDF no disponible: {e}")

    # --- TAB 2: PANEL GLOBAL (ADMIN) ---
    if st.session_state.user_role == "admin":
        with tab_global:
            st.subheader("🌎 Estado Global")
            
            # --- CÁLCULOS PARA GRÁFICOS GLOBALES ---
            global_cumple, global_atraso = 0, 0
            data_profesionales = []
            resumen_global_maestro = []

            for p in sorted(df_c['Profesional'].unique()):
                df_p = df_c[df_c['Profesional'] == p]
                p_cumple, p_atraso = 0, 0
                for c in df_p['Caso'].unique():
                    envios_c = df_e[df_e['Caso'] == c]
                    f_ing_c = df_c[df_c['Caso'] == c].iloc[0]['Fecha Ingreso']
                    f_ref = pd.to_datetime(envios_c['Fecha Envio Real']).max().date() if not envios_c.empty else f_ing_c
                    
                    m_ant = (hoy.year - f_ing_c.year) * 12 + (hoy.month - f_ing_c.month)
                    if hoy.day < f_ing_c.day: m_ant -= 1
                    
                    if (hoy - f_ref).days <= 90: p_cumple += 1
                    else: p_atraso += 1
                    
                    # Cálculo de edad a partir de fechanacimiento
                    try:
                        f_nac = pd.to_datetime(df_c[df_c['Caso'] == c].iloc[0].get('fechanacimiento'), errors='coerce')
                        edad = hoy.year - f_nac.year - ((hoy.month, hoy.day) < (f_nac.month, f_nac.day)) if pd.notnull(f_nac) else "S/I"
                    except:
                        edad = "S/I"

                    resumen_global_maestro.append({
                        "Caso": c, "RIT": df_c[df_c['Caso'] == c].iloc[0]['RIT'],
                        "Profesional": p, "Meses": m_ant, "Edad": edad,
                        "codnino": df_c[df_c['Caso'] == c].iloc[0].get('codnino', 'S/I')
                    })

                global_cumple += p_cumple
                global_atraso += p_atraso
                data_profesionales.append({"Profesional": p, "Al día": p_cumple, "Fuera de plazo": p_atraso})

            # --- MÉTRICAS ---
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Casos", global_cumple + global_atraso)
            c2.metric("Cumplimiento Global", f"{(global_cumple/(global_cumple + global_atraso))*100:.1f}%" if (global_cumple + global_atraso) > 0 else "0%")
            c3.metric("Casos Fuera de Plazo", global_atraso)

            # --- GRÁFICOS ---
            st.divider()
            col_g1, col_g2 = st.columns([2, 1])
            with col_g1:
                fig_comp = px.bar(pd.DataFrame(data_profesionales), x="Profesional", y=["Al día", "Fuera de plazo"], 
                                  color_discrete_map={"Al día": COLOR_VERDE_IRIDEM, "Fuera de plazo": COLOR_GRIS_IRIDEM}, 
                                  barmode="group", text_auto=True)
                fig_comp.update_layout(xaxis_tickangle=-45, height=400, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_comp, use_container_width=True)
            with col_g2:
                fig_global_pie = go.Figure(data=[go.Pie(labels=['Al día', 'Fuera de plazo'], values=[global_cumple, global_atraso], hole=.5, marker_colors=[COLOR_VERDE_IRIDEM, COLOR_GRIS_IRIDEM])])
                fig_global_pie.update_layout(height=350, showlegend=True, legend=dict(orientation="h", y=-0.1, xanchor="center", x=0.5), paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_global_pie, use_container_width=True)

            # --- BUSCADOR RÁPIDO ---
            st.divider()
            st.subheader("🔍 Buscador Rápido de Casos")
            df_maestro_search = pd.DataFrame(resumen_global_maestro)
            criterio = st.radio("Criterio de búsqueda:", ["Nombre del Caso", "Causa RIT", "Cod. Niño"], horizontal=True)
            col_filtro = 'Caso' if criterio == "Nombre del Caso" else ('RIT' if criterio == "Causa RIT" else 'codnino')
            seleccion = st.selectbox("Escribe o selecciona:", ["---"] + sorted(df_maestro_search[col_filtro].astype(str).unique()))
            
            if seleccion != "---":
                info_c = df_maestro_search[df_maestro_search[col_filtro].astype(str) == seleccion].iloc[0]
                edad_txt = f"{info_c['Edad']} años" if info_c['Edad'] != "S/I" else "S/I"
                st.markdown(f"""
                    <div class="case-info-banner">
                        <b>🆔 Cod. Niño:</b> {info_c['codnino']} | <b>👤 Caso:</b> {info_c['Caso']} | <b>🎂 Edad:</b> {edad_txt} | <b>📄 RIT:</b> {info_c['RIT']} | <b>🤝 Profesional:</b> {info_c['Profesional']} | <b>⏱️ Antigüedad:</b> {info_c['Meses']} meses
                    </div>
                """, unsafe_allow_html=True)

            st.divider()
            st.subheader("📋 Lista Maestra")
            st.dataframe(df_c, use_container_width=True, hide_index=True)
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button("📥 Descargar Matriz Completa (Excel)", convertir_a_excel_completo(df_c, df_e), "Matriz_Completa_FAE.xlsx")
            with col_dl2:
                df_lista_simple = df_c[["Caso", "Profesional"]].copy().sort_values("Caso").reset_index(drop=True)
                df_lista_simple.insert(0, "N°", range(1, len(df_lista_simple) + 1))
                output_simple = io.BytesIO()
                with pd.ExcelWriter(output_simple, engine='openpyxl') as writer:
                    df_lista_simple.to_excel(writer, index=False, sheet_name='Lista_Simple')
                st.download_button("📋 Descargar Lista Simple (Excel)", output_simple.getvalue(), "Lista_Simple_FAE.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    # --- TAB 3: LISTA DE ESPERA ---
    if st.session_state.user_role == "admin":
        with tab_espera:
            st.subheader("⏳ Casos en Lista de Espera")
            df_le = cargar_lista_espera()
            if not df_le.empty:
                hoy_le = datetime.now().date()
                df_le['Días en Lista de Espera'] = df_le['FechaIngresoLE'].apply(
                    lambda f: (hoy_le - f).days if pd.notnull(f) else None
                )
                # Cálculo de edad a partir de FechaNacimiento
                def _calcular_edad_le(f_nac):
                    if pd.isnull(f_nac):
                        return None
                    return hoy_le.year - f_nac.year - ((hoy_le.month, hoy_le.day) < (f_nac.month, f_nac.day))
                if 'FechaNacimiento' in df_le.columns:
                    df_le['Edad'] = df_le['FechaNacimiento'].apply(_calcular_edad_le)
                # Mover las nuevas columnas justo después de sus fechas de referencia para mejor lectura
                cols_le = list(df_le.columns)
                if 'FechaIngresoLE' in cols_le and 'Días en Lista de Espera' in cols_le:
                    cols_le.remove('Días en Lista de Espera')
                    idx_ing = cols_le.index('FechaIngresoLE')
                    cols_le.insert(idx_ing + 1, 'Días en Lista de Espera')
                if 'FechaNacimiento' in cols_le and 'Edad' in cols_le:
                    cols_le.remove('Edad')
                    idx_nac = cols_le.index('FechaNacimiento')
                    cols_le.insert(idx_nac + 1, 'Edad')
                df_le = df_le[cols_le]
                st.info(f"Actualmente hay **{len(df_le)}** niños/as en lista de espera.")
                st.dataframe(df_le, use_container_width=True, hide_index=True)
            else: st.success("No hay casos en lista de espera.")

            # --- REGISTRAR CASO DESDE LISTA DE ESPERA ---
            st.divider()
            st.subheader("➕ Registrar Caso desde Lista de Espera")
            df_le_reg = cargar_lista_espera()
            if not df_le_reg.empty:
                opciones_le = {}
                for idx, r in df_le_reg.iterrows():
                    nombre_completo = f"{r.get('Nombres', '')} {r.get('Apellido_Paterno', '')} {r.get('Apellido_Materno', '')}".strip()
                    rit_ref = r.get('RIT', 'S/R') if pd.notnull(r.get('RIT')) else "S/R"
                    opciones_le[f"{nombre_completo} - RIT {rit_ref}"] = idx

                seleccion_le = st.selectbox(
                    "Selecciona a la persona de la Lista de Espera",
                    ["---"] + list(opciones_le.keys()),
                    key="sel_le_a_caso"
                )

                if seleccion_le != "---":
                    fila_le = df_le_reg.loc[opciones_le[seleccion_le]]
                    nombre_sugerido = f"{fila_le.get('Nombres', '')} {fila_le.get('Apellido_Paterno', '')} {fila_le.get('Apellido_Materno', '')}".strip()
                    rit_sugerido = str(fila_le.get('RIT', '')) if pd.notnull(fila_le.get('RIT')) else ""
                    fecnac_le = fila_le.get('FechaNacimiento')
                    fecnac_sugerida = fecnac_le if pd.notnull(fecnac_le) else datetime.now()

                    with st.form("form_le_a_caso"):
                        caso_nombre_nuevo = st.text_input("Nombre del Caso", nombre_sugerido)
                        rit_nuevo = st.text_input("Causa RIT", rit_sugerido)
                        codnino_nuevo = st.text_input("Cod. Niño")
                        fecnac_nuevo = st.date_input("Fecha de Nacimiento", fecnac_sugerida, min_value=datetime(1990, 1, 1))
                        prof_nuevo = st.selectbox("Profesional", PROF_BASE, key="prof_le_a_caso")
                        f_ing_nuevo = st.date_input("Fecha Ingreso", datetime.now(), key="fing_le_a_caso")

                        if st.form_submit_button("✅ Registrar como Caso y eliminar de Lista de Espera") and caso_nombre_nuevo:
                            try:
                                tribunal_le = fila_le.get('Tribunal')
                                comuna_le = fila_le.get('ComunaNiño_a')
                                nuevo_caso = {
                                    "Caso": str(caso_nombre_nuevo).strip(),
                                    "RIT": str(rit_nuevo).strip(),
                                    "codnino": str(codnino_nuevo).strip(),
                                    "fechanacimiento": str(fecnac_nuevo),
                                    "Profesional": prof_nuevo,
                                    "Fecha Ingreso": str(f_ing_nuevo),
                                    "Tribunal": str(tribunal_le).strip() if pd.notnull(tribunal_le) else "S/I",
                                    "Comuna": str(comuna_le).strip() if pd.notnull(comuna_le) else "S/I",
                                }
                                supabase.table("casos").insert(nuevo_caso).execute()

                                # Eliminar el registro correspondiente de la Lista de Espera
                                if 'id' in fila_le.index and pd.notnull(fila_le.get('id')):
                                    supabase.table("lista_espera").delete().eq("id", fila_le['id']).execute()
                                else:
                                    supabase.table("lista_espera").delete().match({
                                        "Nombres": fila_le.get('Nombres'),
                                        "Apellido_Paterno": fila_le.get('Apellido_Paterno'),
                                        "Apellido_Materno": fila_le.get('Apellido_Materno'),
                                    }).execute()

                                st.success(f"✅ Caso '{caso_nombre_nuevo}' registrado y eliminado de la Lista de Espera")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error al registrar: {e}")
            else:
                st.caption("No hay personas en la Lista de Espera para registrar como caso.")

    # --- TAB 4: ANALÍTICA SIS ---
    if st.session_state.user_role == "admin":
        with tab_sis:
            st.link_button("📊 Abrir Analítica SIS (versión completa)", "https://gestion-fae.richardronck.workers.dev/", use_container_width=True)
            st.caption("Se abre en una pestaña nueva. Abajo se muestra la versión integrada en este dashboard, si está disponible.")
            st.divider()
            if os.path.exists(SIS_HTML_FILE):
                with open(SIS_HTML_FILE, 'r', encoding='utf-8') as f:
                    components.html(f.read(), height=1200, scrolling=True)
            else: st.warning("Archivo de analítica no encontrado.")

    # --- TAB 5: AUTOMATIZADOR WORD ---
    with tab_word:
        st.link_button("📝 Abrir Automatizador Word (versión completa)", "https://automatizador-rf-wvfwwtdka7rkyxkmu68ca2.streamlit.app/", use_container_width=True)
        st.caption("Se abre en una pestaña nueva. Abajo está la versión integrada en este dashboard.")
        st.divider()
        st.subheader("📝 Automatizador de Documentos Word")
        opcion_plantilla = st.selectbox("Selecciona la plantilla:", ["Informe de evaluación", "Registro de intervención", "Subir propia (.docx)"])
        plantilla_final = "plantilla.docx" if opcion_plantilla == "Informe de evaluación" else ("plantilla_2.docx" if opcion_plantilla == "Registro de intervención" else st.file_uploader("Sube plantilla", type=["docx"]))
        
        uploaded_excel = st.file_uploader("Sube tu archivo Excel con los datos", type=["xlsx"])
        if uploaded_excel and plantilla_final:
            df_word_raw = pd.read_excel(uploaded_excel)
            df_word_raw.columns = limpiar_y_asegurar_unicos(df_word_raw.columns)
            st.write(f"🔍 Datos detectados: {len(df_word_raw)} filas.")
            
            if st.button("🚀 Generar y Descargar Documentos"):
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for idx, fila in df_word_raw.iterrows():
                        data_dict = {k: limpiar_dato_word(v, k) for k, v in fila.items()}
                        if 'descripcionevento' in data_dict:
                            data_dict['objetivo'] = extraer_objetivo_al_inicio(data_dict['descripcionevento'])
                            data_dict['descripcionevento'] = limpiar_descripcion_original(data_dict['descripcionevento'])
                        
                        doc = DocxTemplate(plantilla_final)
                        doc.render(data_dict)
                        doc_io = io.BytesIO()
                        doc.save(doc_io)
                        
                        name = f"{data_dict.get('nombres', 'Doc')}_{idx+1}.docx"
                        zip_file.writestr(name, doc_io.getvalue())
                
                st.success("✅ ¡Documentos generados!")
                st.download_button("📥 Descargar ZIP", zip_buffer.getvalue(), "documentos_generados.zip", "application/zip")

else:
    st.info("Sube tu Excel para comenzar.")
