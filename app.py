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
# --- CONEXIÓN A SUPABASE ---
# Reemplaza lo que está entre comillas con los datos que copiaste de Supabase
# --- CONEXIÓN DE DIAGNÓSTICO ---
URL_SUPABASE = "https://bnypthionhjtcllbanl.supabase.co"
KEY_SUPABASE = st.secrets["supabase"]["key"]

# Creamos el "mensajero" que llevará y traerá datos
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

# Rutas de Archivos de Base de Datos
CASOS_FILE = "casos.csv"
ENTREGAS_FILE = "entregas.csv"
LISTA_ESPERA_FILE = "lista_espera.csv"
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

# Lista Maestra de Profesionales (Actualizado: Alan Zamora)
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
# --- 6. FUNCIONES DE DATOS Y EXPORTACIÓN ---
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
        
        # Si la base de datos está vacía, devolvemos el molde con columnas
        if df.empty:
            columnas = ["Caso", "RIT", "Profesional", "Fecha Ingreso"] + COLUMNAS_EXTENDIDAS
            return pd.DataFrame(columns=columnas)
        
        # Convertimos las fechas y limpiamos
        df['Fecha Ingreso'] = pd.to_datetime(df['Fecha Ingreso']).dt.date
        df['Caso'] = df['Caso'].astype(str).str.strip()
        
        return df.dropna(subset=['Caso', 'Fecha Ingreso']).drop_duplicates(subset=['Caso'])
    except Exception as e:
        # Si hay error de conexión, también devolvemos el molde vacío
        columnas = ["Caso", "RIT", "Profesional", "Fecha Ingreso"] + COLUMNAS_EXTENDIDAS
        return pd.DataFrame(columns=columnas)

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
    if os.path.exists(LISTA_ESPERA_FILE):
        return pd.read_csv(LISTA_ESPERA_FILE)
    return pd.DataFrame()

def convertir_a_excel_completo(df_casos_actuales, df_entregas_total):
    output = io.BytesIO()
    if not df_entregas_total.empty:
        df_pivot = df_entregas_total.pivot(index='Caso', columns='Informe', values='Fecha Envio Real')
    else:
        df_pivot = pd.DataFrame(columns=NOMBRES_TABLA)
    
    df_final = df_casos_actuales.merge(df_pivot, on='Caso', how='left')
    
    for col in NOMBRES_TABLA:
        if col not in df_final.columns:
            df_final[col] = None
            
    cols_base = ["codnino", "Caso", "fechanacimiento", "RIT", "Nacionalidad", "CalidadJuridica", "DireccionNino", "Comuna", "Tribunal", "ConQuienVive", "Profesional", "Fecha Ingreso"]
    cols_orden = [c for c in cols_base if c in df_final.columns] + NOMBRES_TABLA
    df_final = df_final.reindex(columns=cols_orden)
    
    for col in df_final.columns:
        if "Fecha" in col or col in NOMBRES_TABLA or col == "fechanacimiento":
            df_final[col] = pd.to_datetime(df_final[col], errors='coerce').dt.strftime('%d-%m-%Y').replace("NaT", "")
            
    df_final.insert(0, "N°", range(1, len(df_final) + 1))
    if "Fecha Ingreso" in df_final.columns:
        df_final = df_final.rename(columns={"Fecha Ingreso": "Fecha de Ingreso"})
        
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Listado_Completo')
        ws = writer.sheets['Listado_Completo']
        for col in ws.columns:
            max_len = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_len: 
                        max_len = len(str(cell.value))
                except: 
                    pass
            ws.column_dimensions[column].width = max_len + 2
    return output.getvalue()

def convertir_a_excel_simple(df):
    output = io.BytesIO()
    df_simple = df[["#", "Caso", "Profesional", "Fecha Ingreso", "RIT"]].copy()
    df_simple['Fecha Ingreso'] = pd.to_datetime(df_simple['Fecha Ingreso']).dt.strftime('%d-%m-%Y')
    df_simple = df_simple.rename(columns={"#": "N°", "Fecha Ingreso": "Fecha de Ingreso"})
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_simple.to_excel(writer, index=False, sheet_name='Nomina_FAE')
        ws = writer.sheets['Nomina_FAE']
        for col in ws.columns:
            max_len = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_len: 
                        max_len = len(str(cell.value))
                except: 
                    pass
            ws.column_dimensions[column].width = max_len + 2
    return output.getvalue()

# ==============================================================================
# --- 7. FUNCIONES PDF ---
# ==============================================================================
def generar_pdf_visual(prof_nombre, df_resumen, data_grafico_barras, cumple_count, no_cumple_count):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(213, 219, 219) 
    pdf.rect(0, 0, 210, 45, 'F')
    pdf.set_text_color(49, 51, 63) 
    pdf.set_font("helvetica", "B", 18)
    pdf.cell(0, 15, "CONTROL DE PLAZOS Y CUMPLIMIENTO DE ENTREGAS", ln=True, align="C")
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(120, 150, 40) 
    pdf.cell(0, 10, "FAE DEM CERRILLOS", ln=True, align="C")
    pdf.set_text_color(49, 51, 63)
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 10, f"Profesional: {prof_nombre} | Generado: {datetime.now().strftime('%d-%m-%Y')}", ln=True, align="C")
    pdf.ln(15)
    try:
        plt.figure(figsize=(10, 5))
        df_bar = pd.DataFrame(data_grafico_barras)
        colores_bar = [COLOR_VERDE_IRIDEM if t == "Días desde último envío" else COLOR_GRIS_IRIDEM for t in df_bar['Tipo']]
        bars = plt.bar(df_bar['Caso'], df_bar['Días'], color=colores_bar)
        plt.bar_label(bars, padding=3, fontweight='bold', fontsize=9)
        plt.axhline(y=90, color='#ff7f7f', linestyle='-', linewidth=2)
        plt.xticks(rotation=45, ha='right', fontsize=8)
        plt.title("Dias desde ultimo envio por caso", fontsize=14, fontweight='bold')
        plt.ylim(0, max(df_bar['Días'].max() * 1.2, 110))
        plt.tight_layout()
        img_bar_buf = io.BytesIO()
        plt.savefig(img_bar_buf, format='png', dpi=150)
        plt.close()
        pdf.image(img_bar_buf, x=10, w=190)
        pdf.ln(5)
        plt.figure(figsize=(5, 5))
        values = [cumple_count, no_cumple_count]
        patches, texts, autotexts = plt.pie(values, labels=['Al dia', 'Fuera de plazo'], autopct=lambda pct: f"{int(round(pct/100.*sum(values)))}\n({pct:.1f}%)", colors=[COLOR_VERDE_IRIDEM, COLOR_GRIS_IRIDEM], startangle=90)
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_weight('bold')
        plt.title("Estado de Cumplimiento Operativo", fontsize=12, fontweight='bold')
        img_pie_buf = io.BytesIO()
        plt.savefig(img_pie_buf, format='png', dpi=150)
        plt.close()
        pdf.image(img_pie_buf, x=60, w=90)
    except: pass
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(93, 109, 126)
    pdf.cell(0, 15, "RESUMEN DE PROXIMAS ENTREGAS", ln=True)
    anchos = [45, 22, 22, 28, 25, 30, 18] 
    titulos = ["Caso", "Prox. Inf.", "F. Limite", "Est. (Ingreso)", "Venc. (3m)", "Est. (Operativo)", "Meses"]
    pdf.set_font("helvetica", "B", 8)
    pdf.set_fill_color(213, 219, 219) 
    pdf.set_text_color(0, 0, 0)
    for i, t in enumerate(titulos): pdf.cell(anchos[i], 10, t, border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_font("helvetica", "", 7)
    for _, row in df_resumen.iterrows():
        pdf.cell(anchos[0], 8, str(row['Caso'])[:28], border=1)
        pdf.cell(anchos[1], 8, str(row['Próximo Informe']), border=1, align="C")
        pdf.cell(anchos[2], 8, str(row['F. Límite (Teo)']), border=1, align="C")
        if "VENCIDO" in str(row['Estado (Ingreso)']): pdf.set_text_color(200, 0, 0)
        else: pdf.set_text_color(0, 0, 0)
        pdf.cell(anchos[3], 8, str(row['Estado (Ingreso)']).replace("🔴 ","").replace("🟠 ","").replace("⚪ ",""), border=1, align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.cell(anchos[4], 8, str(row['Venc. (3m)']), border=1, align="C")
        if "VENCIDO" in str(row['Estado (Operativo)']): pdf.set_text_color(200, 0, 0)
        else: pdf.set_text_color(39, 174, 96)
        pdf.cell(anchos[5], 8, str(row['Estado (Operativo)']).replace("🔴 ","").replace("🟢 ",""), border=1, align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.cell(anchos[6], 8, str(row['Meses']), border=1, align="C")
        pdf.ln()
    return pdf.output()

def generar_pdf_cronograma(caso_nombre, f_ingreso, df_hitos):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(213, 219, 219)
    pdf.rect(0, 0, 210, 40, 'F')
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "CRONOGRAMA COMPLETO DE INFORMES", ln=True, align="C")
    pdf.set_font("helvetica", "", 11)
    pdf.cell(0, 8, f"Caso: {caso_nombre}", ln=True, align="C")
    pdf.cell(0, 8, f"Fecha Ingreso: {f_ingreso.strftime('%d-%m-%Y')}", ln=True, align="C")
    pdf.ln(15)
    pdf.set_font("helvetica", "B", 8)
    pdf.set_fill_color(49, 51, 63)
    pdf.set_text_color(255, 255, 255)
    anchos = [30, 30, 30, 45, 35, 25]
    headers = ["Informe", "F. Limite", "F. Envio", "Desfase", "F. Corresp.", "Vigencia"]
    for i, h in enumerate(headers): pdf.cell(anchos[i], 10, h, border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("helvetica", "", 7)
    for _, row in df_hitos.iterrows():
        vig = str(row['Vigencia (3m)']).replace("🟢 ","").replace("🔴 ","").replace("⚪ ","")
        desf = str(row['Desfase']).replace("⚠️ ","").replace("✅ ","")
        pdf.cell(anchos[0], 8, str(row['Informe']), border=1, align="C")
        pdf.cell(anchos[1], 8, str(row['Fecha Límite']), border=1, align="C")
        pdf.cell(anchos[2], 8, str(row['Fecha Envío Real']), border=1, align="C")
        pdf.cell(anchos[3], 8, desf[:30], border=1, align="C")
        pdf.cell(anchos[4], 8, str(row['Fecha Corresponde']), border=1, align="C")
        pdf.cell(anchos[5], 8, vig, border=1, align="C")
        pdf.ln()
    return pdf.output()

# ==============================================================================
# --- 8. BARRA LATERAL (GESTIÓN) ---
# ==============================================================================
if st.session_state.user_role == "admin":
    st.sidebar.header("1. Registrar Nuevo Caso")
    with st.sidebar.form("nuevo_caso", clear_on_submit=True):
        n_caso = st.text_input("Nombre del Caso")
        n_rit = st.text_input("Causa RIT")
        prof = st.selectbox("Profesional", PROF_BASE)
        f_ing = st.date_input("Fecha Ingreso", datetime.now())
        if st.form_submit_button("Guardar Caso") and n_caso:
                nuevo_registro = {
                    "Caso": str(n_caso).strip(), 
                    "RIT": str(n_rit).strip(), 
                    "Profesional": prof, 
                    "Fecha Ingreso": str(f_ing)
                }
                try:
                    supabase.table("casos").insert(nuevo_registro).execute()
                    st.sidebar.success(f"✅ Caso {n_caso} guardado en la nube")
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"❌ Error al guardar: {e}")
                st.rerun()
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
            
            # Columnas adicionales de la Ficha Clínica
            c_codnino = cols_norm.get("codnino")
            c_nacimiento = cols_norm.get("fechanacimiento")

            if not c_caso or not c_prof or not c_fecha:
                st.sidebar.error("⚠️ El Excel debe tener: 'Caso', 'Profesional' y 'Fecha Ingreso'")
            else:
                if st.sidebar.button("🚀 Sincronizar Matriz Completa"):
                    barra_progreso = st.sidebar.progress(0)
                    
                    if modo_reinicio:
                        st.sidebar.warning("Limpiando base de datos...")
                        supabase.table("entregas").delete().neq("id", 0).execute()
                        supabase.table("casos").delete().neq("id", 0).execute()
                    
                    filas = df_excel.iterrows()
                    total = len(df_excel)
                    
                    for i, (idx, row) in enumerate(filas):
                        nombre_c = str(row[c_caso]).strip()
                        f_ing_dt = pd.to_datetime(row[c_fecha], errors='coerce', dayfirst=True)
                        f_ing_val = f_ing_dt.strftime('%Y-%m-%d') if pd.notnull(f_ing_dt) else None
                        
                        if f_ing_val:
                            # Datos del Caso
                            datos_caso = {
                                "Caso": nombre_c,
                                "RIT": str(row[c_rit]).strip() if c_rit else "S/R",
                                "Profesional": str(row[c_prof]).strip(),
                                "Fecha Ingreso": f_ing_val,
                                "codnino": str(row[c_codnino]).strip() if c_codnino else "S/I",
                                "fechanacimiento": str(row[c_nacimiento]).strip() if c_nacimiento else "S/I"
                            }
                            supabase.table("casos").upsert(datos_caso, on_conflict="Caso").execute()
                            
                            # Datos de Informes
                            for inf in NOMBRES_TABLA:
                                col_inf = cols_norm.get(inf.lower())
                                if col_inf and pd.notnull(row[col_inf]):
                                    f_env_dt = pd.to_datetime(row[col_inf], errors='coerce', dayfirst=True)
                                    if pd.notnull(f_env_dt):
                                        envio = {
                                            "Caso": nombre_c, 
                                            "Informe": inf, 
                                            "Fecha Envio Real": f_env_dt.strftime('%Y-%m-%d')
                                        }
                                        supabase.table("entregas").upsert(envio, on_conflict="Caso, Informe").execute()
                        
                        barra_progreso.progress((i + 1) / total)
                    
                    st.sidebar.success("✅ ¡Sincronización Exitosa!")
                    st.rerun()
        except Exception as e:
            st.sidebar.error(f"Error: {e}")
st.sidebar.header("3. Registrar Envío")
df_casos_sidebar = cargar_casos()
if st.session_state.user_role != "admin":
    df_casos_sidebar = df_casos_sidebar[df_casos_sidebar['Profesional'] == st.session_state.user_name]

if not df_casos_sidebar.empty:
    with st.sidebar.form("registrar_envio", clear_on_submit=True):
        caso_envio = st.selectbox("Selecciona el Caso", sorted(df_casos_sidebar['Caso'].unique()))
        informe_envio = st.selectbox("¿Qué informe envió?", NOMBRES_TABLA)
        f_envio = st.date_input("Fecha Real de Envío", datetime.now())
        if st.form_submit_button("Registrar Envío"):
            df_e_load = cargar_entregas()
            df_e_load = df_e_load[~((df_e_load['Caso'] == caso_envio) & (df_e_load['Informe'] == informe_envio))]
            nuevo_e = pd.DataFrame([{"Caso": caso_envio, "Informe": informe_envio, "Fecha Envio Real": f_envio}])
            pd.concat([df_e_load, nuevo_e]).to_csv(ENTREGAS_FILE, index=False)
            st.rerun()

if st.session_state.user_role == "admin":
    st.sidebar.divider()
    st.sidebar.header("4. 🗑️ Eliminar Caso")
    if not df_casos_sidebar.empty:
        lista_borrar = sorted(df_casos_sidebar['Caso'].unique())
        caso_a_borrar = st.sidebar.selectbox("Caso a eliminar", ["---"] + lista_borrar)
        if st.sidebar.button("Eliminar permanentemente"):
            if caso_a_borrar != "---":
                df_c_nuevo = df_casos_sidebar[df_casos_sidebar['Caso'] != caso_a_borrar]
                df_c_nuevo.to_csv(CASOS_FILE, index=False)
                df_e_actual = cargar_entregas()
                df_e_actual[df_e_actual['Caso'] != caso_a_borrar].to_csv(ENTREGAS_FILE, index=False)
                st.sidebar.warning(f"Caso '{caso_a_borrar}' eliminado.")
                st.rerun()

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
                        df_c_all = cargar_casos()
                        df_e_all = cargar_entregas()
                        mask = df_c_all['Caso'] == caso_a_editar
                        df_c_all.loc[mask, ['Caso', 'RIT', 'Profesional', 'Fecha Ingreso']] = [nuevo_nombre_c.strip(), nuevo_rit, nuevo_prof, nueva_fecha_ing]
                        df_c_all.to_csv(CASOS_FILE, index=False)
                        if nuevo_nombre_c.strip() != caso_a_editar:
                            df_e_all.loc[df_e_all['Caso'] == caso_a_editar, 'Caso'] = nuevo_nombre_c.strip()
                            df_e_all.to_csv(ENTREGAS_FILE, index=False)
                        st.success("Información actualizada correctamente.")
                        st.rerun()

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
                    df_e_corr.loc[(df_e_corr['Caso'] == caso_f_corr) & (df_e_corr['Informe'] == inf_a_corr), 'Fecha Envio Real'] = nueva_f_corr
                    df_e_corr.to_csv(ENTREGAS_FILE, index=False)
                    st.success("Fecha actualizada.")
                    st.rerun()
            with c_del:
                if st.button("🗑️ Eliminar Informe"):
                    df_e_nuevo = df_e_corr[~((df_e_corr['Caso'] == caso_f_corr) & (df_e_corr['Informe'] == inf_a_corr))]
                    df_e_nuevo.to_csv(ENTREGAS_FILE, index=False)
                    st.warning("Registro eliminado.")
                    st.rerun()

    st.sidebar.divider()
    st.sidebar.header("6. ⏳ Cargar Lista de Espera")
    archivo_espera = st.sidebar.file_uploader("Subir Excel Lista Espera", type=["xlsx"])
    if archivo_espera:
        try:
            df_espera_raw = pd.read_excel(archivo_espera)
            cols_interes = ["Nombres", "Apellido_Paterno", "Apellido_Materno", "FechaNacimiento", "Rut", "FechaIngresoLE", "Tribunal", "RIT", "FechaOrden", "ComunaNiño_a"]
            df_espera_filtrado = df_espera_raw[[c for c in cols_interes if c in df_espera_raw.columns]]
            if st.sidebar.button("🔄 Actualizar Lista de Espera"):
                df_espera_filtrado.to_csv(LISTA_ESPERA_FILE, index=False)
                st.sidebar.success("Lista de espera actualizada.")
                st.rerun()
        except Exception as e: 
            st.sidebar.error(f"Error al procesar lista de espera: {e}")

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
                        "Caso": c, 
                        "Días": (hoy - ultima_fecha).days, 
                        "Tipo": etiqueta, 
                        "Fecha Referencia": ultima_fecha.strftime('%d-%m-%Y'), 
                        "Meses en Programa": f"{meses_ant} meses",
                        "Límite 3 meses": vencimiento_3m.strftime('%d-%m-%Y')
                    })
                
                df_grafico = pd.DataFrame(data_grafico_barras)
                max_y = max(df_grafico['Días'].max() * 1.2, 120)
                fig_barras = px.bar(df_grafico, x='Caso', y='Días', color='Tipo', text='Días', 
                                   hover_name=None,
                                   hover_data={
                                       'Caso': False, 
                                       'Tipo': False, 
                                       'Días': False, 
                                       'Fecha Referencia': True, 
                                       'Meses en Programa': True,
                                       'Límite 3 meses': True
                                   },
                                   color_discrete_map={"Días desde último envío": COLOR_VERDE_IRIDEM, "días desde ingreso (Diagnóstico)": COLOR_GRIS_IRIDEM})
                fig_barras.add_hline(y=90, line_color="#ff7f7f", line_width=2)
                
                fig_barras.update_layout(
                    xaxis_tickangle=-45, 
                    height=400, 
                    margin=dict(t=30, b=100, l=50, r=10), 
                    yaxis_range=[0, max_y], 
                    paper_bgcolor='rgba(0,0,0,0)', 
                    plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(automargin=True)
                )
                fig_barras.update_traces(textposition='outside', textfont_size=11, textfont_weight="bold")
                
                evento_clic = st.plotly_chart(fig_barras, use_container_width=True, on_select="rerun")
                if evento_clic and len(evento_clic.selection.points) > 0:
                    st.session_state.caso_seleccionado = evento_clic.selection.points[0]['x']

            cumple_count, no_cumple_count = 0, 0
            detalles_pendientes_ind = []

            for c in df_c_filtrado['Caso'].unique():
                envios_caso = df_e[df_e['Caso'] == c]
                f_ing_c = df_c[df_c['Caso'] == c].iloc[0]['Fecha Ingreso']
                f_ref = pd.to_datetime(envios_caso['Fecha Envio Real']).max().date() if not envios_caso.empty else f_ing_c
                venc_op_dt = (pd.to_datetime(f_ref) + pd.DateOffset(months=3)).date()
                
                if hoy <= venc_op_dt: 
                    cumple_count += 1
                else: 
                    no_cumple_count += 1
                    entregados_lista = envios_caso['Informe'].tolist()
                    idx_proximo = max([NOMBRES_TABLA.index(inf) for inf in entregados_lista if inf in NOMBRES_TABLA]) + 1 if entregados_lista else 0
                    if idx_proximo < len(NOMBRES_TABLA):
                        proximo_inf = NOMBRES_TABLA[idx_proximo]
                        m_ant = (hoy.year - f_ing_c.year) * 12 + (hoy.month - f_ing_c.month)
                        if hoy.day < f_ing_c.day: m_ant -= 1
                        detalles_pendientes_ind.append({
                            "Caso": c, 
                            "RIT": df_c[df_c['Caso'] == c].iloc[0]['RIT'],
                            "Próximo Informe": proximo_inf,
                            "Venc. (3m)": venc_op_dt.strftime('%d-%m-%Y'),
                            "Meses": m_ant
                        })

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
                    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
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
            
            caso_sel_raw = st.selectbox("2. Caso seleccionado:", lista_con_marca, index=idx_sel, key="selector_caso_principal")
            caso_sel = caso_sel_raw.replace("📍 ", "")
            st.session_state.caso_seleccionado = caso_sel
            
            datos_c = df_c[df_c['Caso'] == caso_sel].iloc[0]
            f_ingreso = datos_c['Fecha Ingreso']
            rit_c = datos_c['RIT'] if 'RIT' in datos_c else "S/R"
            m_ant_tit = (hoy.year - f_ingreso.year) * 12 + (hoy.month - f_ingreso.month)
            if hoy.day < f_ingreso.day: m_ant_tit -= 1
            
            es_seleccionado_grafico = (st.session_state.caso_seleccionado == caso_sel)
            clase_banner = "case-info-banner case-info-highlight" if es_seleccionado_grafico else "case-info-banner"
            nombre_display = f"📍 <b>{caso_sel}</b>" if es_seleccionado_grafico else caso_sel
            
            st.markdown(f"""<div class="{clase_banner}"><b>Caso:</b> {nombre_display} | <b>RIT:</b> {rit_c} | <b>Ingreso:</b> {f_ingreso.strftime('%d-%m-%Y')} | <b>Antigüedad:</b> {m_ant_tit} meses</div>""", unsafe_allow_html=True)

            hitos_inicial, hitos_larga = [], []
            for i, nombre_inf in enumerate(NOMBRES_TABLA):
                fecha_limite = (pd.to_datetime(f_ingreso) + pd.DateOffset(months=3 * (i + 1))).date()
                reg_e = df_e[(df_e['Caso'] == caso_sel) & (df_e['Informe'] == nombre_inf)]
                if i == 0: f_ref_ope = f_ingreso
                else:
                    reg_prev = df_e[(df_e['Caso'] == caso_sel) & (df_e['Informe'] == NOMBRES_TABLA[i-1])]
                    f_ref_ope = reg_prev.iloc[0]['Fecha Envio Real'] if not reg_prev.empty else None
                
                if f_ref_ope:
                    venc_ope_dt = (pd.to_datetime(f_ref_ope) + pd.DateOffset(months=3)).date()
                    venc_ope_str = venc_ope_dt.strftime('%d-%m-%Y')
                    vigencia_str = "🟢 VIGENTE" if hoy <= venc_ope_dt else "🔴 VENCIDO"
                else:
                    venc_ope_str, vigencia_str = "-", "⚪ PENDIENTE"
                
                dias_res = (fecha_limite - hoy).days
                f_envio_str, desfase_str, estado = "-", "-", ""
                if not reg_e.empty:
                    f_real = reg_e.iloc[0]['Fecha Envio Real']
                    f_envio_str = f_real.strftime('%d-%m-%Y')
                    desfase = (f_real - fecha_limite).days
                    desfase_str, estado = (f"✅ A tiempo ({abs(desfase)} días)", "🟢 ENTREGADO") if desfase <= 0 else (f"⚠️ Retraso de {desfase} días", "🟡 ENTREGADO CON ATRASO")
                else:
                    if dias_res < 0: estado, desfase_str = "🔴 PENDIENTE VENCIDO", f"Atrasado por {abs(dias_res)} días"
                    elif dias_res <= 15: estado, desfase_str = "🟠 PRÓXIMO A VENCER", f"Faltan {dias_res} días"
                    else: estado, desfase_str = "⚪ EN PLAZO", f"Faltan {dias_res} días"
                
                fila = {"Informe": nombre_inf, "Fecha Límite": fecha_limite.strftime('%d-%m-%Y'), "Fecha Envío Real": f_envio_str, "Desfase": desfase_str, "Fecha Corresponde": venc_ope_str, "Vigencia (3m)": vigencia_str}
                if i < 7: hitos_inicial.append(fila)
                elif not reg_e.empty or dias_res <= 180: hitos_larga.append(fila)

            def style_func(val):
                if "🔴" in str(val): return 'background-color: #ffcccc'
                if "🟢" in str(val): return 'background-color: #ccffcc'
                if "🟡" in str(val): return 'background-color: #ffffcc'
                if "🟠" in str(val): return 'background-color: #ffe5cc'
                return ''

            conf_detalle = {"Informe": st.column_config.Column(width="small", alignment="center"), "Fecha Límite": st.column_config.Column(width="small", alignment="center"), "Fecha Envío Real": st.column_config.Column(width="small", alignment="center"), "Desfase": st.column_config.Column(width="medium", alignment="center"), "Fecha Corresponde": st.column_config.Column(width="small", alignment="center"), "Vigencia (3m)": st.column_config.Column(width="small", alignment="center")}
            
            st.write("### ⏱️ Cronograma de Informes")
            df_full_hitos = pd.concat([pd.DataFrame(hitos_inicial), pd.DataFrame(hitos_larga)])
            # --- CANDADO DE SEGURIDAD PARA EL PDF ---
            if caso_sel and caso_sel != "---":
                try:
                    pdf_cron_bytes = generar_pdf_cronograma(caso_sel, f_ingreso, df_full_hitos)
                    st.download_button(
                        label="📥 Descargar Cronograma Completo (PDF)", 
                        data=pdf_cron_bytes, 
                        file_name=f"Cronograma_{caso_sel}.pdf", 
                        mime="application/pdf"
                    )
                except Exception as e:
                    st.warning("Selecciona un caso válido para generar el cronograma.")
            st.dataframe(pd.DataFrame(hitos_inicial)[["Informe", "Fecha Límite", "Fecha Envío Real", "Desfase", "Fecha Corresponde", "Vigencia (3m)"]].style.map(style_func, subset=['Vigencia (3m)']), use_container_width=True, hide_index=True, column_config=conf_detalle)
            if hitos_larga:
                st.markdown("---")
                st.write("### 🏠 Larga Permanencia")
                st.dataframe(pd.DataFrame(hitos_larga)[["Informe", "Fecha Límite", "Fecha Envío Real", "Desfase", "Fecha Corresponde", "Vigencia (3m)"]].style.map(style_func, subset=['Vigencia (3m)']), use_container_width=True, hide_index=True, column_config=conf_detalle)

            # --- CUADROS A Y B (RESUMEN GENERAL SEPARADO) ---
            st.divider()
            resumen_maestro_pdf = [] 

            for _, row in df_c_filtrado.iterrows():
                c_nombre, f_ing = row['Caso'], row['Fecha Ingreso']
                entregas_caso = df_e[df_e['Caso'] == c_nombre]
                entregados_lista = entregas_caso['Informe'].tolist()
                indices_entregados = [NOMBRES_TABLA.index(inf) for inf in entregados_lista if inf in NOMBRES_TABLA]
                idx_proximo = max(indices_entregados) + 1 if indices_entregados else 0
                
                m_ant = (hoy.year - f_ing.year) * 12 + (hoy.month - f_ing.month)
                if hoy.day < f_ing.day: m_ant -= 1

                if idx_proximo < len(NOMBRES_TABLA):
                    proximo_inf = NOMBRES_TABLA[idx_proximo]
                    ultima_fecha_ref = pd.to_datetime(entregas_caso['Fecha Envio Real']).max().date() if not entregas_caso.empty else f_ing
                    fecha_venc_op = (pd.to_datetime(ultima_fecha_ref) + pd.DateOffset(months=3)).date()
                    estado_operativo = "🔴 VENCIDO" if hoy > fecha_venc_op else "🟢 VIGENTE"
                    fecha_limite_teorica = (pd.to_datetime(f_ing) + pd.DateOffset(months=3 * (idx_proximo + 1))).date()
                    dias_faltantes = (fecha_limite_teorica - hoy).days
                    estado_ingreso = "🔴 VENCIDO" if dias_faltantes < 0 else ("🟠 PRÓXIMO" if dias_faltantes <= 15 else "⚪ EN PLAZO")
                    
                    resumen_maestro_pdf.append({
                        "Caso": c_nombre, "Próximo Informe": proximo_inf, "F. Límite (Teo)": fecha_limite_teorica.strftime('%d-%m-%Y'), 
                        "Estado (Ingreso)": estado_ingreso, "Venc. (3m)": fecha_venc_op.strftime('%d-%m-%Y'), 
                        "Estado (Operativo)": estado_operativo, "Meses": f"{m_ant}", "Días": dias_faltantes
                    })
            
            df_maestro_vista = pd.DataFrame(resumen_maestro_pdf)

            if not df_maestro_vista.empty:
                st.subheader(f"📋 A. Próximas Entregas (Según último envío - 3 meses)")
                df_op_vista = df_maestro_vista[["Caso", "Próximo Informe", "Venc. (3m)", "Estado (Operativo)", "Meses"]].rename(columns={"Venc. (3m)": "Vencimiento (3 meses)", "Estado (Operativo)": "Estado Operativo"})
                st.dataframe(df_op_vista.style.map(lambda v: 'color: #d63031; font-weight: bold' if "🔴" in str(v) else '', subset=['Estado Operativo']), use_container_width=True, hide_index=True)

                st.subheader(f"📋 B. Próximas Entregas (Según fecha de ingreso)")
                df_ing_vista = df_maestro_vista[["Caso", "Próximo Informe", "F. Límite (Teo)", "Días", "Estado (Ingreso)"]].rename(columns={"F. Límite (Teo)": "Fecha Límite (Ingreso)", "Días": "Días Restantes", "Estado (Ingreso)": "Estado Ingreso"})
                st.dataframe(df_ing_vista.style.map(lambda v: 'color: #d63031; font-weight: bold' if "🔴" in str(v) else '', subset=['Estado Ingreso']), use_container_width=True, hide_index=True)

                # --- SEGUNDO CANDADO DE SEGURIDAD (REPORTE EJECUTIVO) ---
                try:
                    pdf_bytes = generar_pdf_visual(prof_sel, df_maestro_vista, data_grafico_barras, cumple_count, no_cumple_count)
                    st.download_button(
                        label="📥 Descargar Reporte PDF Ejecutivo", 
                        data=pdf_bytes, 
                        file_name=f"Reporte_{prof_sel}.pdf", 
                        mime="application/pdf"
                    )
                except Exception as e:
                    st.info("El reporte PDF estará disponible al seleccionar un profesional con casos.")

    # --- TAB 2: PANEL GLOBAL (ADMIN) ---
    if st.session_state.user_role == "admin":
        with tab_global:
            st.subheader("🌎 Estado Global")
            global_cumple, global_atraso = 0, 0
            data_profesionales = []
            resumen_global_maestro = [] 

            for p in sorted(df_c['Profesional'].unique()):
                df_p = df_c[df_c['Profesional'] == p]
                p_cumple, p_atraso = 0, 0
                for c in df_p['Caso'].unique():
                    envios_c = df_e[df_e['Caso'] == c]
                    f_ref = pd.to_datetime(envios_c['Fecha Envio Real']).max().date() if not envios_c.empty else df_c[df_c['Caso'] == c].iloc[0]['Fecha Ingreso']
                    f_ing_c = df_c[df_c['Caso'] == c].iloc[0]['Fecha Ingreso']
                    
                    datos_caso_original = df_c[df_c['Caso'] == c].iloc[0]
                    rit_c_global = str(datos_caso_original.get('RIT', 'S/R'))
                    
                    entregados_lista = envios_c['Informe'].tolist()
                    idx_proximo = max([NOMBRES_TABLA.index(inf) for inf in entregados_lista if inf in NOMBRES_TABLA]) + 1 if entregados_lista else 0
                    m_ant = (hoy.year - f_ing_c.year) * 12 + (hoy.month - f_ing_c.month)
                    if hoy.day < f_ing_c.day: m_ant -= 1
                    
                    # CÁLCULO DE EDAD
                    try:
                        f_nac = pd.to_datetime(datos_caso_original.get('fechanacimiento'), errors='coerce').date()
                        edad = hoy.year - f_nac.year - ((hoy.month, hoy.day) < (f_nac.month, f_nac.day)) if pd.notnull(f_nac) else "S/I"
                    except: edad = "S/I"

                    if idx_proximo < len(NOMBRES_TABLA):
                        proximo_inf = NOMBRES_TABLA[idx_proximo]
                        fecha_limite_teorica = (pd.to_datetime(f_ing_c) + pd.DateOffset(months=3 * (idx_proximo + 1))).date()
                        fecha_venc_op = (pd.to_datetime(f_ref) + pd.DateOffset(months=3)).date()
                        dias_faltantes = (fecha_limite_teorica - hoy).days
                        estado_res = "🔴 VENCIDO" if dias_faltantes < 0 else ("🟠 PRÓXIMO" if dias_faltantes <= 15 else "⚪ EN PLAZO")
                        estado_operativo = "🔴 VENCIDO" if hoy > fecha_venc_op else "🟢 VIGENTE"
                        
                        resumen_global_maestro.append({
                            "Caso": c, "RIT": rit_c_global, "Profesional": p, "Fecha Ingreso": f_ing_c, 
                            "Próximo Informe": proximo_inf, "F. Límite (Teo)": fecha_limite_teorica.strftime('%d-%m-%Y'), 
                            "Días": dias_faltantes, "Estado (Ingreso)": estado_res, 
                            "Venc. (3m)": fecha_venc_op.strftime('%d-%m-%Y'), "Estado (Operativo)": estado_operativo, "Meses": f"{m_ant}",
                            "Edad": edad,
                            "codnino": datos_caso_original.get('codnino', 'S/I'),
                            "fechanacimiento": datos_caso_original.get('fechanacimiento', 'S/I'),
                            "Nacionalidad": datos_caso_original.get('Nacionalidad', 'S/I'),
                            "CalidadJuridica": datos_caso_original.get('CalidadJuridica', 'S/I'),
                            "DireccionNino": datos_caso_original.get('DireccionNino', 'S/I'),
                            "Comuna": datos_caso_original.get('Comuna', 'S/I'),
                            "Tribunal": datos_caso_original.get('Tribunal', 'S/I'),
                            "ConQuienVive": datos_caso_original.get('ConQuienVive', 'S/I')
                        })

                    if hoy <= (pd.to_datetime(f_ref) + pd.DateOffset(months=3)).date(): p_cumple += 1
                    else: p_atraso += 1
                
                global_cumple += p_cumple
                global_atraso += p_atraso
                data_profesionales.append({"Profesional": p, "Al día": p_cumple, "Fuera de plazo": p_atraso, "Total": p_cumple + p_atraso})
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Casos", global_cumple + global_atraso)
            c2.metric("Cumplimiento Global", f"{(global_cumple/(global_cumple + global_atraso))*100:.1f}%" if (global_cumple + global_atraso) > 0 else "0%")
            c3.metric("Casos Fuera de Plazo", global_atraso)
            
            st.divider()
            col_g1, col_g2 = st.columns([2, 1])
            df_global_plot = pd.DataFrame(data_profesionales)
            with col_g1:
                fig_comp = px.bar(df_global_plot, x="Profesional", y=["Al día", "Fuera de plazo"], 
                                  color_discrete_map={"Al día": COLOR_VERDE_IRIDEM, "Fuera de plazo": COLOR_GRIS_IRIDEM}, 
                                  barmode="group", text_auto=True)
                fig_comp.update_layout(xaxis_tickangle=-45, height=420, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                
                evento_global = st.plotly_chart(fig_comp, use_container_width=True, on_select="rerun")
                
                if evento_global and len(evento_global.selection.points) > 0:
                    punto = evento_global.selection.points[0]
                    prof_clic = punto['x']
                    serie_clic = punto.get('legendgroup')
                    
                    if serie_clic == "Fuera de plazo":
                        st.warning(f"⚠️ Casos Fuera de Plazo: {prof_clic}")
                        df_maestro_global = pd.DataFrame(resumen_global_maestro)
                        casos_vencidos = df_maestro_global[(df_maestro_global['Profesional'] == prof_clic) & 
                                                           (df_maestro_global['Estado (Operativo)'] == "🔴 VENCIDO")]
                        if not casos_vencidos.empty:
                            st.dataframe(casos_vencidos[["Caso", "RIT", "Próximo Informe", "Venc. (3m)", "Meses"]], 
                                         use_container_width=True, hide_index=True)

            with col_g2:
                fig_global_pie = go.Figure(data=[go.Pie(
                    labels=['Al día', 'Fuera de plazo'], 
                    values=[global_cumple, global_atraso], 
                    hole=.5, 
                    marker_colors=[COLOR_VERDE_IRIDEM, COLOR_GRIS_IRIDEM], 
                    textposition='inside',
                    insidetextorientation='horizontal',
                    textinfo='percent',
                    textfont=dict(size=14, color="white")
                )])
                fig_global_pie.update_layout(height=380, showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5), paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_global_pie, use_container_width=True)

            # --- BUSCADOR RÁPIDO DE CASOS (CON COD. NIÑO) ---
            st.divider()
            st.subheader("🔍 Buscador Rápido de Casos")
            df_maestro_search = pd.DataFrame(resumen_global_maestro)
            criterio = st.radio("Criterio de búsqueda:", ["Nombre del Caso", "Causa RIT", "Cod. Niño"], horizontal=True)
            
            if criterio == "Nombre del Caso":
                lista_busqueda = sorted(df_maestro_search['Caso'].unique())
                seleccion = st.selectbox("Escribe el nombre del niño/a:", ["---"] + lista_busqueda)
                col_filtro = 'Caso'
            elif criterio == "Causa RIT":
                lista_busqueda = sorted(df_maestro_search['RIT'].unique())
                seleccion = st.selectbox("Escribe la Causa RIT:", ["---"] + lista_busqueda)
                col_filtro = 'RIT'
            else: # Cod. Niño
                lista_busqueda = sorted(df_maestro_search['codnino'].unique().astype(str))
                seleccion = st.selectbox("Escribe el Cod. Niño:", ["---"] + lista_busqueda)
                col_filtro = 'codnino'
            
            if seleccion != "---":
                info_c = df_maestro_search[df_maestro_search[col_filtro].astype(str) == seleccion].iloc[0]
                st.markdown(f"""
                    <div class="case-info-banner">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                            <div>
                                <b>🆔 Cod. Niño:</b> {info_c.get('codnino', 'S/I')}<br>
                                <b>👤 Caso:</b> {info_c['Caso']}<br>
                                <b>🎂 F. Nacimiento:</b> {pd.to_datetime(info_c.get('fechanacimiento'), errors='coerce').strftime('%d-%m-%Y') if info_c.get('fechanacimiento') != 'S/I' else 'S/I'}<br>
                                <b>🎂 Edad:</b> {info_c['Edad']} años<br>
                                <b>⚖️ Calidad Jurídica:</b> {info_c.get('CalidadJuridica', 'S/I')}<br>
                                <b>🏠 Con Quién Vive:</b> {info_c.get('ConQuienVive', 'S/I')}
                            </div>
                            <div>
                                <b>📄 Causa RIT:</b> {info_c['RIT']}<br>
                                <b>🏛️ Tribunal:</b> {info_c.get('Tribunal', 'S/I')}<br>
                                <b>📍 Comuna:</b> {info_c.get('Comuna', 'S/I')}<br>
                                <b>🗺️ Dirección:</b> {info_c.get('DireccionNino', 'S/I')}<br>
                                <b>🤝 Profesional / Dupla:</b> {info_c['Profesional']}<br>
                                <b>⏱️ Antigüedad:</b> {info_c['Meses']} meses | <b>Próx. Inf:</b> {info_c['Próximo Informe']} ({info_c['F. Límite (Teo)']})
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

            # --- LISTA MAESTRA ---
            st.divider()
            st.subheader("📋 Detalle de Casos por Profesional")
            opciones_global = ["--- TODOS LOS CASOS (LISTA MAESTRA) ---", "--- VENCIDOS POR 3 MESES (OPERATIVO) ---"] + sorted(df_c['Profesional'].unique())
            prof_global_sel = st.selectbox("Selecciona Profesional/Dupla para ver sus casos:", opciones_global, key="prof_global_sel")
            
            df_res_global = df_maestro_search.copy()
            if prof_global_sel == "--- VENCIDOS POR 3 MESES (OPERATIVO) ---":
                df_res_global = df_res_global[df_res_global['Estado (Operativo)'] == "🔴 VENCIDO"]
            elif prof_global_sel != "--- TODOS LOS CASOS (LISTA MAESTRA) ---":
                df_res_global = df_res_global[df_res_global['Profesional'] == prof_global_sel]
            
            df_res_global['#'] = range(1, len(df_res_global) + 1)

            if not df_res_global.empty:
                col_ex1, col_ex2 = st.columns(2)
                with col_ex1:
                    excel_completo = convertir_a_excel_completo(df_c if prof_global_sel == "--- TODOS LOS CASOS (LISTA MAESTRA) ---" else df_c[df_c['Profesional'] == prof_global_sel], df_e)
                    st.download_button(label="📥 Descargar Matriz Maestra Completa (Excel)", data=excel_completo, file_name=f"Matriz_Completa_FAE.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                with col_ex2:
                    df_nom_simple = df_res_global[["#", "Caso", "Profesional", "Fecha Ingreso", "RIT"]].copy()
                    df_nom_simple['Fecha Ingreso'] = pd.to_datetime(df_nom_simple['Fecha Ingreso']).dt.strftime('%d-%m-%Y')
                    output_s = io.BytesIO()
                    with pd.ExcelWriter(output_s, engine='openpyxl') as writer:
                        df_nom_simple.to_excel(writer, index=False, sheet_name='Nomina_FAE')
                        ws = writer.sheets['Nomina_FAE']
                        for col in ws.columns:
                            max_len = 0
                            column = col[0].column_letter
                            for cell in col:
                                try:
                                    if len(str(cell.value)) > max_len: max_len = len(str(cell.value))
                                except: pass
                            ws.column_dimensions[column].width = max_len + 2
                    st.download_button(label="📋 Descargar Nómina Simple (Excel)", data=output_s.getvalue(), file_name=f"Nomina_Simple.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                
                st.dataframe(df_res_global.style.map(lambda v: 'color: #d63031; font-weight: bold' if "🔴" in str(v) else '', subset=['Estado (Ingreso)', 'Estado (Operativo)']), use_container_width=True, hide_index=True, column_config={"#": st.column_config.Column(width="small", alignment="center"), "Caso": st.column_config.Column(width="medium"), "RIT": st.column_config.Column(width="small", alignment="center"), "Profesional": st.column_config.Column(width="medium"), "Próximo Informe": st.column_config.Column(width="small", alignment="center"), "F. Límite (Teo)": st.column_config.Column(width="small", alignment="center"), "Días": st.column_config.Column(width="small", alignment="center"), "Estado (Ingreso)": st.column_config.Column(width="small", alignment="center"), "Venc. (3m)": st.column_config.Column(width="small", alignment="center"), "Estado (Operativo)": st.column_config.Column(width="small", alignment="center"), "Meses": st.column_config.Column(width="small", alignment="center")})

    # --- TAB 3: LISTA DE ESPERA (ADMIN) ---
    if st.session_state.user_role == "admin":
        with tab_espera:
            st.subheader("⏳ Casos en Lista de Espera")
            df_le = cargar_lista_espera()
            if not df_le.empty:
                df_le['FechaNacimiento'] = pd.to_datetime(df_le['FechaNacimiento'], errors='coerce').dt.date
                df_le['FechaIngresoLE'] = pd.to_datetime(df_le['FechaIngresoLE'], errors='coerce').dt.date
                df_le = df_le.sort_values(by='FechaIngresoLE', ascending=True)
                
                def calc_edad(nac):
                    if pd.isnull(nac): return "-"
                    return hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))
                
                def calc_espera(ing):
                    if pd.isnull(ing): return "-"
                    return f"{(hoy - ing).days} días"

                df_le['Edad'] = df_le['FechaNacimiento'].apply(calc_edad)
                df_le['Tiempo en Espera'] = df_le['FechaIngresoLE'].apply(calc_espera)
                
                cols_finales = ["Nombres", "Apellido_Paterno", "Apellido_Materno", "Edad", "Tiempo en Espera", "Rut", "FechaIngresoLE", "Tribunal", "RIT", "FechaOrden", "ComunaNiño_a"]
                df_le = df_le.reindex(columns=cols_finales)
                
                st.info(f"Actualmente hay **{len(df_le)}** niños/as en lista de espera.")
                st.dataframe(df_le, use_container_width=True, hide_index=True)
            else:
                st.success("No hay casos cargados en la lista de espera.")

    # --- TAB 4: ANALÍTICA SIS (ADMIN) ---
    if st.session_state.user_role == "admin":
        with tab_sis:
            st.subheader("📊 Analítica FAE: Reporte Institucional")
            if os.path.exists(SIS_HTML_FILE):
                with open(SIS_HTML_FILE, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                components.html(html_content, height=1200, scrolling=True)
            else:
                st.warning(f"No se encontró el archivo '{SIS_HTML_FILE}'.")

    # --- TAB 5: AUTOMATIZADOR WORD (TODOS) ---
    with tab_word:
        st.subheader("📝 Automatizador de Documentos Word")
        st.info("Esta herramienta permite generar documentos Word a partir de un Excel y una Plantilla.")
        
        st.markdown("### 1. Configuración de Plantilla")
        opcion_plantilla = st.selectbox(
            "Selecciona la plantilla a usar:",
            ["Informe de evaluación", "Registro de intervención", "Subir mi propia plantilla (.docx)"]
        )

        plantilla_final = None
        if opcion_plantilla == "Subir mi propia plantilla (.docx)":
            uploaded_template = st.file_uploader("Sube tu Plantilla Word personalizada", type=["docx"])
            plantilla_final = uploaded_template
        else:
            nombre_archivo = "plantilla.docx" if opcion_plantilla == "Informe de evaluación" else "plantilla_2.docx"
            if os.path.exists(nombre_archivo):
                plantilla_final = nombre_archivo
            else:
                st.error(f"⚠️ No se encontró el archivo '{nombre_archivo}' en la carpeta del sistema.")

        st.markdown("### 2. Carga de Datos")
        uploaded_excel = st.file_uploader("Sube tu archivo Excel con los datos", type=["xlsx"])
        
        if uploaded_excel and plantilla_final:
            try:
                df_word_raw = pd.read_excel(uploaded_excel)
                df_word_raw.columns = limpiar_y_asegurar_unicos(df_word_raw.columns)
                df_word_filtrado = df_word_raw.copy()
                
                if opcion_plantilla == "Informe de evaluación":
                    df_word_filtrado = df_word_raw.head(1)
                    st.info("💡 Modo Evaluación: Se procesará únicamente la primera fila del archivo.")
                else:
                    st.markdown("### 3. Filtrar Datos")
                    columnas_permitidas = ["apellido_paterno", "apellido_materno", "nombres", "paterno", "materno", "tpaterno", "tmatern", "tnombres"]
                    columnas_disponibles = [c for c in df_word_raw.columns if c in columnas_permitidas]
                    
                    if columnas_disponibles:
                        col_a_filtrar = st.selectbox("Selecciona la columna para filtrar:", ["Sin filtro"] + columnas_disponibles)
                        
                        if col_a_filtrar != "Sin filtro":
                            valores_unicos = sorted(df_word_raw[col_a_filtrar].unique().astype(str))
                            seleccionados = st.multiselect(f"Selecciona valores de '{col_a_filtrar}':", valores_unicos)
                            if seleccionados:
                                df_word_filtrado = df_word_raw[df_word_raw[col_a_filtrar].astype(str).isin(seleccionados)]

                st.write(f"🔍 **Vista previa de los datos detectados ({len(df_word_filtrado)} filas):**")
                st.dataframe(df_word_filtrado.head(5), hide_index=True)
                
                if st.button("🚀 Generar y Descargar Documento(s)"):
                    if opcion_plantilla == "Informe de evaluación":
                        fila = df_word_filtrado.iloc[0]
                        data_dict = {}
                        for k, v in fila.items():
                            data_dict[k] = limpiar_dato_word(v, k)
                        
                        if 'descripcionevento' in data_dict:
                            data_dict['objetivo'] = extraer_objetivo_al_inicio(data_dict['descripcionevento'])
                            data_dict['descripcionevento'] = limpiar_descripcion_original(data_dict['descripcionevento'])
                        
                        doc = DocxTemplate(plantilla_final)
                        doc.render(data_dict)
                        
                        doc_io = io.BytesIO()
                        doc.save(doc_io)
                        doc_io.seek(0)
                        
                        st.success("✅ Informe generado con éxito.")
                        st.download_button(
                            label="📥 Descargar Informe (.docx)",
                            data=doc_io.getvalue(),
                            file_name="Informe_Evaluacion.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        )
                    else:
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                            for idx, fila in df_word_filtrado.iterrows():
                                data_dict = {}
                                for k, v in fila.items():
                                    data_dict[k] = limpiar_dato_word(v, k)
                                
                                if 'descripcionevento' in data_dict:
                                    data_dict['objetivo'] = extraer_objetivo_al_inicio(data_dict['descripcionevento'])
                                    data_dict['descripcionevento'] = limpiar_descripcion_original(data_dict['descripcionevento'])
                                
                                doc = DocxTemplate(plantilla_final)
                                doc.render(data_dict)
                                doc_io = io.BytesIO()
                                doc.save(doc_io)
                                
                                name = f"{data_dict.get('nombres', '')}_{data_dict.get('apellido_paterno', '')}".strip()
                                name = name if name else f"Registro_{idx+1}"
                                
                                zip_file.writestr(f"Registro_{name}.docx", doc_io.getvalue())
                        
                        zip_buffer.seek(0)
                        st.success(f"✅ ¡{len(df_word_filtrado)} documentos generados!")
                        st.download_button(
                            label="📥 Descargar ZIP",
                            data=zip_buffer.getvalue(),
                            file_name="documentos_generados.zip",
                            mime="application/zip"
                        )
            except Exception as e:
                st.error(f"Error crítico al procesar: {e}")

else:
    st.info("Sube tu Excel para comenzar.")