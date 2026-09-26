"""
gestion_salas.py
----------------
Módulo de planificación de salas/duplas, pensado para insertarse como una pestaña
dentro de app.py (llamando a render_gestion_salas()) en vez de ejecutarse como app
independiente.

Persistencia:
Cada mes se guarda como UN SOLO registro JSON en la tabla 'planificacion_salas' de
Supabase (columnas: mes_id, datos). Requiere que exista esa tabla (ver instrucciones
entregadas junto con este archivo) y que se le pase el cliente 'supabase' ya conectado
(el mismo que usa app.py) a render_gestion_salas().
"""

import pandas as pd
import random
import streamlit as st
import altair as alt
from io import BytesIO
from datetime import datetime, timedelta

# Intentar importar icalendar de forma segura
try:
    from icalendar import Calendar, Event
    ICAL_DISPONIBLE = True
except ImportError:
    ICAL_DISPONIBLE = False

# --- 1. CONFIGURACIÓN GENERAL ---
AÑO_INICIO = 2026
MES_INICIO = 8

BLOQUES = ["B1 9-10hrs", "B2 10-11hrs", "B3 11-12hrs", "B4 12-13hrs", "B5 14-15hrs", "B6 15-16hrs", "B7 16-17hrs"]

HORARIOS_BLOQUES = {
    "B1 9-10hrs": (9, 10), "B2 10-11hrs": (10, 11), "B3 11-12hrs": (11, 12),
    "B4 12-13hrs": (12, 13), "B5 14-15hrs": (14, 15), "B6 15-16hrs": (15, 16),
    "B7 16-17hrs": (16, 17)
}

# Bloques de la mañana vs. de la tarde, usados para alternar el turno semana a semana
BLOQUES_MANANA = BLOQUES[:4]   # B1 a B4 (9:00 a 13:00)
BLOQUES_TARDE = BLOQUES[4:]    # B5 a B7 (14:00 a 17:00)

# Tope de bloques dobles consecutivos que puede acumular UNA MISMA dupla en un día.
# Da continuidad (no quedan "salteados") sin dejar que una sola dupla acapare el día completo.
MAX_DOBLES_CONSECUTIVOS_DIA = 2

NOMBRES_DUPLAS = {
    "D1": "Bruno-Ignacia A", "D2": "Daniela-Paula", "D3": "Francisca-Tiare",
    "D4": "Laura-Alan", "D5": "Maida-Vale", "D6": "Marcelo-Cony", "D7": "Sol-Fran"
}

def obtener_iniciales(id_dupla):
    if id_dupla in NOMBRES_DUPLAS:
        nombre = NOMBRES_DUPLAS[id_dupla]
        partes = nombre.split("-")
        return "-".join([p[0].upper() for p in partes])
    return id_dupla

COLORES_DUPLAS = {
    "D1": "#1E88E5", "D2": "#2E7D32", "D3": "#8E24AA", "D4": "#D84315",
    "D5": "#C2185B", "D6": "#00838F", "D7": "#E64A19", "---": "#CCCCCC",
    "T Disp": "#757575", "L": "#B0B0B0", "CERRADO": "#D32F2F"
}

DUPLAS = list(NOMBRES_DUPLAS.keys())
SALAS = ["S1", "S2", "S3"]
DIAS_NOMBRE = ["Lun", "Mar", "Mié", "Jue", "Vie"]

# RESTRICCIÓN: Teletrabajo (TT) - Bruno (D4) Lunes y Viernes
TELETRABAJO = {
    "Lun": ["D3", "D7", "D1", "D4"],
    "Mar": [],
    "Mié": ["D3", "D2", "D6"],
    "Jue": ["D6", "D5", "D4"],
    "Vie": ["D2", "D5", "D7", "D1"]
}

# --- 2. LÓGICA DE PERSISTENCIA (Supabase) ---
def guardar_datos(supabase):
    """Guarda cada mes como un registro JSON en la tabla 'planificacion_salas'."""
    for id_m, m_data in st.session_state.meses_data.items():
        registro = {
            'df': m_data['df'].to_dict(orient='records'),
            'rt': m_data['rt'],
            'bloqueos': m_data['bloqueos'],
            'fijado': m_data['fijado'],
            'año': m_data['año'],
            'mes': m_data['mes']
        }
        try:
            supabase.table("planificacion_salas").upsert(
                {"mes_id": id_m, "datos": registro},
                on_conflict="mes_id"
            ).execute()
        except Exception as e:
            st.error(f"❌ No se pudo guardar la planificación de '{id_m}' en Supabase: {e}")

def cargar_datos(supabase):
    """Lee todos los meses guardados en 'planificacion_salas'. Devuelve None si la
    tabla está vacía o si hay un error de conexión (en ese caso se generan meses nuevos)."""
    try:
        response = supabase.table("planificacion_salas").select("*").execute()
        filas = response.data
        if not filas:
            return None
        datos_cargados = {}
        for fila in filas:
            id_m = fila["mes_id"]
            registro = dict(fila["datos"])
            registro['df'] = pd.DataFrame(registro['df'])
            datos_cargados[id_m] = registro
        return datos_cargados
    except Exception as e:
        st.warning(f"⚠️ No se pudo leer la planificación de salas desde Supabase. Detalle: {e}")
        return None

def borrar_todo_supabase(supabase):
    try:
        supabase.table("planificacion_salas").delete().neq("mes_id", "").execute()
        return True
    except Exception as e:
        st.error(f"❌ No se pudo borrar la planificación en Supabase: {e}")
        return False

# --- 3. LÓGICA DE MÉTRICAS ---
def calcular_metricas(df):
    totales_sala = df[df["Dupla"].str.startswith("D")].groupby("Dupla").size().to_dict()
    df_horas = df[df["Dupla"].str.startswith("D")].drop_duplicates(subset=['Fecha', 'Bloque', 'Dupla'])
    horas_reales = df_horas.groupby("Dupla").size().to_dict()
    dobles_df = df[df["Dupla"].str.startswith("D")].groupby(['Fecha', 'Bloque', 'Dupla']).size().reset_index(name='count')
    dobles = dobles_df[dobles_df['count'] > 1].groupby('Dupla').size().to_dict()
    df_terrenos = df[df["T_Diario"].str.startswith("D")].drop_duplicates(subset=['Fecha'])
    terrenos = df_terrenos.groupby("T_Diario").size().to_dict()
    return totales_sala, horas_reales, dobles, terrenos

# --- 4. LÓGICA DE FECHAS Y TERRENOS ---
def obtener_dias_mes(año, mes):
    dias = []
    fecha = datetime(año, mes, 1)
    while fecha.month == mes:
        if fecha.weekday() < 5:
            dias.append({
                "fecha_str": f"{DIAS_NOMBRE[fecha.weekday()]} {fecha.day:02d}",
                "nombre_dia": DIAS_NOMBRE[fecha.weekday()],
                "semana": fecha.isocalendar()[1]
            })
        fecha += timedelta(days=1)
    return dias

def asignar_terrenos_mensuales(dias_habiles, dict_bloqueos, año, mes):
    for intento in range(100):
        mapping = {dia["fecha_str"]: "T Disp" for dia in dias_habiles}
        semanas_asignadas = {d: [] for d in DUPLAS}
        conteo_dupla = {d: 0 for d in DUPLAS}
        for f_str, info in dict_bloqueos.items():
            if len(info['bloques']) == len(BLOQUES): mapping[f_str] = "CERRADO"
            elif len(info['bloques']) > 0: mapping[f_str] = "T Disp"
        if año == 2026 and mes == 8 and mapping.get("Lun 03") == "T Disp":
            mapping["Lun 03"] = "D3"; conteo_dupla["D3"] += 1
            sem_d3 = next(d["semana"] for d in dias_habiles if d["fecha_str"] == "Lun 03")
            semanas_asignadas["D3"].append(sem_d3)
        duplas_lista = list(DUPLAS)
        random.shuffle(duplas_lista)
        posible = True
        for d in duplas_lista:
            while conteo_dupla[d] < 2:
                candidatos = [dia["fecha_str"] for dia in dias_habiles if mapping[dia["fecha_str"]] == "T Disp" and d not in TELETRABAJO[dia["nombre_dia"]] and dia["semana"] not in semanas_asignadas[d] and (dia["semana"]-1 not in semanas_asignadas[d]) and (dia["semana"]+1 not in semanas_asignadas[d])]
                if not candidatos: posible = False; break
                elegido = random.choice(candidatos)
                mapping[elegido] = d; conteo_dupla[d] += 1
                semanas_asignadas[d].append(next(dia["semana"] for dia in dias_habiles if dia["fecha_str"] == elegido))
            if not posible: break
        if posible: return mapping, []
    return mapping, []

# --- 5. MOTOR DE GENERACIÓN (REDISEÑADO: MIN 10, MAX 14, ANTICONCENTRACIÓN,
#          CONTINUIDAD DE DOBLES Y ALTERNANCIA DE TURNO SEMANAL) ---
def generar_calendario_mensual(año, mes, dict_bloqueos):
    dias_mes = obtener_dias_mes(año, mes)
    mapping_terrenos, reuniones_t = asignar_terrenos_mensuales(dias_mes, dict_bloqueos, año, mes)
    uso_mensual = {d: 0 for d in DUPLAS}
    uso_dobles_mensual = {d: 0 for d in DUPLAS}
    data = []

    # --- Alternancia de turno (mañana/tarde) semana a semana ---
    # turno_previo: turno que predominó en la última semana ya cerrada de cada dupla.
    # horas_turno_semana: acumulado de bloques por turno de la semana EN CURSO.
    turno_previo = {d: None for d in DUPLAS}
    horas_turno_semana = {d: {"mañana": 0, "tarde": 0} for d in DUPLAS}
    semana_actual = None

    # --- Alternancia del horario de los BLOQUES DOBLES, por día de la semana ---
    # Registra en qué turno (mañana/tarde) tuvo cada dupla su último bloque doble
    # en cada día de la semana (Lun..Vie), a lo largo de TODO el mes. Así, si a una
    # dupla le vuelve a tocar doble el mismo día de la semana (ej. otro miércoles),
    # se prioriza invertir el horario en vez de repetir siempre el mismo tramo.
    ultimo_turno_doble_dia_semana = {d: {dia: None for dia in DIAS_NOMBRE} for d in DUPLAS}

    for dia in dias_mes:
        f_str = dia["fecha_str"]; n_dia = dia["nombre_dia"]; sem = dia["semana"]

        # Al cambiar de semana ISO, se "cierra" la anterior: se fija cuál fue el turno
        # dominante de cada dupla para penalizarlo (no repetirlo) en la semana que empieza.
        if semana_actual is not None and sem != semana_actual:
            for d in DUPLAS:
                h_m = horas_turno_semana[d]["mañana"]
                h_t = horas_turno_semana[d]["tarde"]
                if h_m or h_t:
                    turno_previo[d] = "mañana" if h_m >= h_t else "tarde"
                # Si la dupla no tuvo bloques esa semana (ej. días cerrados), se conserva
                # el turno_previo que ya tenía de la última semana en que sí trabajó.
            horas_turno_semana = {d: {"mañana": 0, "tarde": 0} for d in DUPLAS}
        semana_actual = sem

        t_diario = mapping_terrenos.get(f_str) or "T Disp"
        uso_hoy = {d: 0 for d in DUPLAS} # Reset diario para obligar a rotar duplas

        # --- Continuidad de bloques dobles dentro del día ---
        # Si un bloque queda con doble, se intenta que la MISMA dupla siga en el/los
        # bloque(s) inmediatamente siguiente(s) (hasta el tope MAX_DOBLES_CONSECUTIVOS_DIA)
        # para que los dobles queden seguidos en el horario y no "salteados".
        racha_doble_dupla = None
        racha_doble_len = 0
        racha_doble_idx = None

        if t_diario == "CERRADO":
            motivo = dict_bloqueos.get(f_str, {}).get('motivo', "DÍA CERRADO")
            for b in BLOQUES:
                for s in SALAS: data.append({"Semana": sem, "Fecha": f_str, "T_Diario": "CERRADO", "Bloque": b, "Ubicación": s, "Dupla": motivo})
            continue

        # Pool de duplas que no están en terreno hoy
        pool_dia = [d for d in DUPLAS if d != t_diario]

        for idx_b, b in enumerate(BLOQUES):
            turno_actual = "mañana" if b in BLOQUES_MANANA else "tarde"

            if f_str in dict_bloqueos and b in dict_bloqueos[f_str]['bloques']:
                motivo = dict_bloqueos[f_str]['motivo']
                for s in SALAS: data.append({"Semana": sem, "Fecha": f_str, "T_Diario": t_diario, "Bloque": b, "Ubicación": s, "Dupla": motivo})
                # Un bloque bloqueado corta cualquier racha de dobles en curso
                racha_doble_dupla = None; racha_doble_len = 0; racha_doble_idx = None
                continue

            asignacion_bloque = {"S1": "---", "S2": "---", "S3": "---"}
            candidatos_bloque = list(pool_dia)

            # Regla D6 Lunes
            if n_dia == "Lun" and b == BLOQUES[1] and "D6" in candidatos_bloque:
                asignacion_bloque["S1"] = "D6"; candidatos_bloque.remove("D6")

            # 1. ASIGNAR BLOQUE DOBLE (Prioridad: < 10, Límite Estricto: 14)
            # Solo duplas que NO están en Teletrabajo hoy pueden hacer bloques dobles
            candidatos_dobles = [c for c in candidatos_bloque if c not in TELETRABAJO[n_dia] and uso_dobles_mensual[c] < 14]

            # ¿Seguimos la racha de dobles del bloque anterior con la misma dupla?
            continuar_racha = (
                racha_doble_dupla is not None
                and racha_doble_idx == idx_b - 1
                and racha_doble_len < MAX_DOBLES_CONSECUTIVOS_DIA
                and racha_doble_dupla in candidatos_dobles
            )

            if continuar_racha:
                d_doble = racha_doble_dupla
            else:
                # Primero se intenta SOLO con quienes invertirían el turno respecto a su
                # último doble el mismo día de semana (ej. si el miércoles pasado fue
                # 9-11, hoy se prioriza que sea 14-17). Si nadie cumple eso (ej. solo
                # queda 1 candidata elegible ese día), se cae al resto de candidatas.
                invierten = [c for c in candidatos_dobles if ultimo_turno_doble_dia_semana[c][n_dia] != turno_actual]
                pool_dobles = invierten if invierten else candidatos_dobles

                # Dentro de ese pool: primero los que no llegaron al mínimo de 10 dobles,
                # luego por cantidad de dobles acumulados, turno de la semana pasada,
                # y uso hoy/mes para diversidad
                pool_dobles.sort(key=lambda x: (
                    uso_dobles_mensual[x] >= 10,
                    uso_dobles_mensual[x],
                    1 if turno_previo[x] == turno_actual else 0,
                    uso_hoy[x],
                    uso_mensual[x],
                ))
                d_doble = pool_dobles[0] if pool_dobles else None
                d_doble = candidatos_dobles[0] if candidatos_dobles else None

            if d_doble:
                # Intentar el doble (S1-S3 o S2-S3)
                if asignacion_bloque["S1"] == "---":
                    asignacion_bloque["S1"] = d_doble; asignacion_bloque["S3"] = d_doble
                else:
                    asignacion_bloque["S2"] = d_doble; asignacion_bloque["S3"] = d_doble

                uso_dobles_mensual[d_doble] += 1
                candidatos_bloque.remove(d_doble)

                if d_doble == racha_doble_dupla and racha_doble_idx == idx_b - 1:
                    racha_doble_len += 1
                else:
                    # Es el INICIO de una racha nueva (no la continuación de la anterior):
                    # se registra el turno para poder invertirlo la próxima vez que a esta
                    # dupla le toque doble el mismo día de la semana.
                    racha_doble_len = 1
                    ultimo_turno_doble_dia_semana[d_doble][n_dia] = turno_actual
                racha_doble_dupla = d_doble
                racha_doble_idx = idx_b
            else:
                racha_doble_dupla = None; racha_doble_len = 0; racha_doble_idx = None

            # 2. LLENADO TOTAL INDIVIDUAL (Incluye duplas en Teletrabajo)
            # Ordenamos por uso_hoy para obligar a rotar y no concentrar solo dos duplas;
            # entre empatados, se prioriza a quien NO tuvo este mismo turno la semana pasada
            candidatos_bloque.sort(key=lambda x: (
                uso_hoy[x],
                1 if turno_previo[x] == turno_actual else 0,
                uso_mensual[x],
                random.random(),
            ))

            for s in SALAS:
                if asignacion_bloque[s] == "---" and candidatos_bloque:
                    dupla_elegida = candidatos_bloque.pop(0)
                    asignacion_bloque[s] = dupla_elegida

            # 3. GUARDAR Y ACTUALIZAR CONTADORES
            for s in SALAS:
                dupla_final = asignacion_bloque[s]
                data.append({"Semana": sem, "Fecha": f_str, "T_Diario": t_diario, "Bloque": b, "Ubicación": s, "Dupla": dupla_final})
                if dupla_final in DUPLAS:
                    uso_mensual[dupla_final] += 1
                    uso_hoy[dupla_final] += 1
                    horas_turno_semana[dupla_final][turno_actual] += 1

    return pd.DataFrame(data), reuniones_t

# --- 6. RENDERIZADORES HTML ---
def render_tabla_dia(df_dia, fecha_str, dict_bloqueos, foco_duplas=[]):
    t_diario = df_dia["T_Diario"].iloc[0] if not df_dia.empty else "T Disp"
    style_td_base = "border: 1px solid #ddd; font-size: 12px; padding: 4px 2px; text-align: center; height: 32px;"
    style_th = "border: 1px solid #ccc; font-size: 11px; padding: 6px; background: #f1f3f5; height: 28px; color: #444;"
    html = f"""<table style="width:100%; border-collapse: collapse; table-layout: fixed; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
        <thead><tr><th style="width: 35%; {style_th}">Bloque</th><th style="{style_th}">S1</th><th style="{style_th}">S2</th><th style="{style_th}">S3</th></tr></thead><tbody>"""
    es_dia_cerrado_completo = (fecha_str in dict_bloqueos and len(dict_bloqueos[fecha_str]['bloques']) == len(BLOQUES)) or (t_diario == "CERRADO")
    for idx, bloque in enumerate(BLOQUES):
        html += f"<tr><td style='{style_td_base} background: #fcfcfc; color: #666;'>{bloque}</td>"
        if es_dia_cerrado_completo:
            if idx == 0:
                motivo = dict_bloqueos[fecha_str]['motivo'] if (fecha_str in dict_bloqueos) else df_dia["Dupla"].iloc[0]
                html += f"""<td colspan="3" rowspan="7" style="{style_td_base} background-color: #FFF3E0; color: #E65100; vertical-align: middle; font-weight: bold; font-size: 14px;">{motivo}</td>"""
        elif fecha_str in dict_bloqueos and bloque in dict_bloqueos[fecha_str]['bloques']:
            html += f"""<td colspan="3" style="{style_td_base} background-color: #FFF3E0; color: #E65100; font-weight: bold;">{dict_bloqueos[fecha_str]['motivo']}</td>"""
        else:
            for s in SALAS:
                res = df_dia[(df_dia["Bloque"] == bloque) & (df_dia["Ubicación"] == s)]
                dupla = res["Dupla"].values[0] if not res.empty else "---"
                texto_mostrar = obtener_iniciales(dupla) if dupla.startswith("D") else dupla
                color_t = COLORES_DUPLAS.get(dupla, "#333")
                bg_c = "#e7f3ff" if (not foco_duplas or dupla in foco_duplas) and dupla.startswith("D") else "#ffffff"
                op = "1" if not foco_duplas or dupla in foco_duplas else "0.2"
                html += f"<td style='{style_td_base} background-color: {bg_c}; color: {color_t}; font-weight: 800; opacity: {op};'>{texto_mostrar}</td>"
        html += "</tr>"
    return html + "</tbody></table>"

def render_resumen_mensual(df_total, foco_duplas=[]):
    t_sala, h_real, dbl, terr = calcular_metricas(df_total)
    max_h = max(h_real.values()) if h_real else 0
    html = """<div style='background: #ffffff; padding: 8px; border-radius: 8px; border: 2px solid #1565C0; margin-top: 15px; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); width: fit-content; margin-left: auto; margin-right: auto;'>
              <p style='margin: 0 0 8px 0; font-size: 14px; font-weight: bold; color: #1565C0; text-align: center; display: block;'>🏆 RESUMEN MENSUAL (Horas Reales vs Salas)</p>
              <div style='display: flex; justify-content: center; flex-wrap: wrap; gap: 5px;'>"""
    for d in DUPLAS:
        color = COLORES_DUPLAS[d]
        box_style = f"background: #E3F2FD; border: 1px solid {color}; border-radius: 4px;" if d in foco_duplas else ("opacity: 0.35;" if foco_duplas else "border-right: 1px solid #eee;")
        brecha = max_h - h_real.get(d, 0)
        brecha_style = "color: #D32F2F; font-weight: bold;" if brecha > 4 else "color: #2E7D32;"
        html += f"""<div style='text-align: center; padding: 4px 8px; min-width: 85px; {box_style}'>
                        <span style='color: {color}; font-weight: bold; font-size: 15px;'>{d}</span><br>
                        <span style='font-size: 12px; color: #333; font-weight: bold;'>{h_real.get(d,0)}h</span>
                        <span style='font-size: 10px; color: #666;'>({t_sala.get(d,0)}s)</span><br>
                        <span style='font-size: 10px; color: #E65100; font-weight: bold;'>{terr.get(d,0)} Terr</span><br>
                        <span style='font-size: 9px; {brecha_style}'>Dif: -{brecha}h</span><br>
                        <span style='font-size: 10px; color: #1565C0; font-weight: 700;'>({dbl.get(d,0)}/10-14 dbl)</span>
                    </div>"""
    return html + "</div></div>"

def render_resumen_semanal(df_sem, foco_duplas=[]):
    _, h_real, dbl, _ = calcular_metricas(df_sem)
    html = """<div style='background: #f9f9f9; padding: 10px; border-radius: 5px; border: 1px solid #eee; margin-top: -10px; margin-bottom: 20px;'>
              <div style='display: flex; justify-content: space-around; flex-wrap: wrap;'>"""
    for d in DUPLAS:
        opacity = "1" if (not foco_duplas or d in foco_duplas) else "0.3"
        html += f"""<div style='text-align: center; padding: 5px 10px; opacity: {opacity};'>
                        <span style='color: {COLORES_DUPLAS[d]}; font-weight: bold; font-size: 14px;'>{d}</span>:
                        <span style='font-size: 12px; color: #666;'>{h_real.get(d,0)}h <small>({dbl.get(d,0)} dbl)</small></span>
                    </div>"""
    return html + "</div></div>"

def mostrar_grafico_comparativo(df_total, foco_duplas=[]):
    t_sala, h_real, dbl, _ = calcular_metricas(df_total)
    plot_data = []
    for d in DUPLAS:
        if not foco_duplas or d in foco_duplas:
            plot_data.append({"Dupla": d, "Valor": t_sala.get(d, 0), "Tipo": "Bloques Sala"})
            plot_data.append({"Dupla": d, "Valor": h_real.get(d, 0), "Tipo": "Horas Reales"})
            plot_data.append({"Dupla": d, "Valor": dbl.get(d, 0), "Tipo": "Bloques Dobles"})
    if plot_data:
        df_plot = pd.DataFrame(plot_data)
        color_scale = alt.Scale(domain=['Horas Reales', 'Bloques Sala', 'Bloques Dobles'], range=['#D4E157', '#BDBDBD', '#81D4FA'])
        bars = alt.Chart(df_plot).mark_bar().encode(x=alt.X('Tipo:N', title=None, axis=alt.Axis(labels=False)), y=alt.Y('Valor:Q', title=None), color=alt.Color('Tipo:N', scale=color_scale, legend=alt.Legend(title="Métrica", orient="top")))
        text = alt.Chart(df_plot).mark_text(align='center', baseline='bottom', dy=-2, fontWeight='normal', fontSize=10, color='black').encode(x=alt.X('Tipo:N'), y=alt.Y('Valor:Q'), text=alt.Text('Valor:Q'))
        final_chart = alt.layer(bars, text).properties(width=70, height=140).facet(column=alt.Column('Dupla:N', title=None, header=alt.Header(labelOrient='bottom', labelFontSize=11, labelFontWeight='bold'))).configure_view(stroke=None)
        st.altair_chart(final_chart, use_container_width=False)

# --- 7. EXPORTACIÓN EXCEL ---
def exportar_excel_visual(df_total, dict_bloqueos):
    output = BytesIO()
    workbook = pd.ExcelWriter(output, engine='xlsxwriter').book
    worksheet = workbook.add_worksheet('Calendario')
    fmt_header = workbook.add_format({'bold': True, 'bg_color': '#f1f3f5', 'border': 1, 'align': 'center'})
    fmt_summary_title = workbook.add_format({'bold': True, 'bg_color': '#1565C0', 'font_color': 'white', 'border': 1, 'align': 'center'})
    fmt_date = workbook.add_format({'bold': True, 'bg_color': '#ffffff', 'border': 1, 'align': 'center', 'font_size': 12})
    fmt_terrain = workbook.add_format({'bold': True, 'font_color': '#d32f2f', 'border': 1, 'align': 'center', 'font_size': 10})
    fmt_block = workbook.add_format({'bg_color': '#fafafa', 'border': 1, 'font_size': 9})
    fmt_closed = workbook.add_format({'bg_color': '#FFF3E0', 'font_color': '#E65100', 'bold': True, 'border': 1, 'align': 'center', 'valign': 'vcenter'})
    fmt_duplas = {d: workbook.add_format({'bg_color': '#e7f3ff' if d.startswith('D') else '#ffffff', 'font_color': color, 'bold': True, 'border': 1, 'align': 'center'}) for d, color in COLORES_DUPLAS.items()}
    fmt_num = workbook.add_format({'border': 1, 'align': 'center'})
    curr_row = 0
    worksheet.merge_range(curr_row, 0, curr_row, 5, "RESUMEN MENSUAL DE CARGA", fmt_summary_title)
    curr_row += 1
    headers = ["Dupla", "Iniciales", "Horas Reales", "Bloques Sala", "Dobles", "Terrenos"]
    for i, h in enumerate(headers): worksheet.write(curr_row, i, h, fmt_header)
    curr_row += 1
    t_sala, h_real, dbls, terrs = calcular_metricas(df_total)
    for d_id in DUPLAS:
        worksheet.write(curr_row, 0, d_id, fmt_duplas.get(d_id)); worksheet.write(curr_row, 1, obtener_iniciales(d_id), fmt_num); worksheet.write(curr_row, 2, h_real.get(d_id, 0), fmt_num); worksheet.write(curr_row, 3, t_sala.get(d_id, 0), fmt_num); worksheet.write(curr_row, 4, dbls.get(d_id, 0), fmt_num); worksheet.write(curr_row, 5, terrs.get(d_id, 0), fmt_num); curr_row += 1
    curr_row += 2
    semanas = df_total["Semana"].unique()
    for sem in semanas:
        worksheet.write(curr_row, 0, f"SEMANA {list(semanas).index(sem) + 1}", fmt_header); curr_row += 1
        df_sem = df_total[df_total["Semana"] == sem]; fechas = df_sem["Fecha"].unique()
        for i, dia_nom in enumerate(DIAS_NOMBRE):
            col_start = i * 4; fecha_act = [f for f in fechas if f.startswith(dia_nom)]
            if fecha_act:
                current_f_str = fecha_act[0]; t_asignado = df_sem[df_sem["Fecha"] == current_f_str]["T_Diario"].iloc[0]
                if t_asignado in ["T Disp", "CERRADO"]:
                    label_t = "Disponible"
                else:
                    label_t = f"{t_asignado}({obtener_iniciales(t_asignado)})"
                worksheet.merge_range(curr_row, col_start, curr_row, col_start + 3, current_f_str, fmt_date); worksheet.merge_range(curr_row + 1, col_start, curr_row + 1, col_start + 3, f"T: {label_t}", fmt_terrain); worksheet.write(curr_row + 2, col_start, "Bloque", fmt_header); worksheet.write(curr_row + 2, col_start + 1, "S1", fmt_header); worksheet.write(curr_row + 2, col_start + 2, "S2", fmt_header); worksheet.write(curr_row + 2, col_start + 3, "S3", fmt_header)
                for b_idx, bloque in enumerate(BLOQUES):
                    r = curr_row + 3 + b_idx; worksheet.write(r, col_start, bloque, fmt_block)
                    if t_asignado == "CERRADO":
                        if b_idx == 0: worksheet.merge_range(r, col_start + 1, r + 6, col_start + 3, df_sem["Dupla"].iloc[0], fmt_closed)
                    elif current_f_str in dict_bloqueos and bloque in dict_bloqueos[current_f_str]['bloques']:
                        worksheet.merge_range(r, col_start + 1, r, col_start + 3, dict_bloqueos[current_f_str]['motivo'], fmt_closed)
                    else:
                        for s_idx, sala_id in enumerate(SALAS):
                            res = df_sem[(df_sem["Fecha"] == current_f_str) & (df_sem["Bloque"] == bloque) & (df_sem["Ubicación"] == sala_id)]
                            if not res.empty:
                                dupla_id = res["Dupla"].values[0]
                                texto_celda = obtener_iniciales(dupla_id) if dupla_id in NOMBRES_DUPLAS else dupla_id
                                worksheet.write(r, col_start + 1 + s_idx, texto_celda, fmt_duplas.get(dupla_id, fmt_duplas["---"]))
        curr_row += 11
        t_sala_s, h_real_s, dbls_s, _ = calcular_metricas(df_sem)
        for idx, d_id in enumerate(DUPLAS):
            col_off = idx * 2; worksheet.write(curr_row + 1, col_off, d_id, fmt_duplas.get(d_id)); worksheet.write(curr_row + 1, col_off + 1, f"{h_real_s.get(d_id, 0)}h ({dbls_s.get(d_id, 0)} dbl)", fmt_num)
        curr_row += 4
    workbook.close()
    return output.getvalue()

def exportar_icalendar(df_total, año, mes):
    if not ICAL_DISPONIBLE: return None
    cal = Calendar(); cal.add('prodid', '-//Gestión de Salas//Fundación DEM//ES'); cal.add('version', '2.0')
    for _, row in df_total.iterrows():
        dupla = row['Dupla']
        if dupla in ["---", "L"]: continue
        event = Event()
        iniciales = obtener_iniciales(dupla)
        sala = row['Ubicación']
        event.add('summary', f"({sala}){iniciales}")
        dia_num = int(row['Fecha'].split(" ")[1])
        h_inicio, h_fin = HORARIOS_BLOQUES[row['Bloque']]
        event.add('dtstart', datetime(año, mes, dia_num, h_inicio, 0, 0))
        event.add('dtend', datetime(año, mes, dia_num, h_fin, 0, 0))
        event.add('description', f"Sala: {sala}. Terreno: {row['T_Diario']}")
        cal.add_component(event)
    return cal.to_ical()

# --- 8. INTERFAZ (para insertar dentro de una pestaña de app.py) ---
def render_gestion_salas(supabase, es_admin=True):
    """Renderiza el módulo completo de gestión de salas dentro del contenedor actual
    (pensado para llamarse dentro de un 'with tab:'). Los controles de edición solo
    se muestran si es_admin=True; la vista del calendario está disponible para todos.

    'supabase' es el cliente ya conectado (el mismo que crea app.py con create_client)."""

    if 'meses_data' not in st.session_state:
        datos_previos = cargar_datos(supabase)
        if datos_previos:
            st.session_state.meses_data = datos_previos
            for m_id in st.session_state.meses_data:
                m_data = st.session_state.meses_data[m_id]
                if 'Dupla' in m_data['df'].columns:
                    if m_data['df']['Dupla'].isin(["R. Técnica", "DÍA DE LA NIÑEZ", "REUNIÓN TÉCNICA"]).any():
                        df_new, rt_new = generar_calendario_mensual(m_data['año'], m_data['mes'], m_data['bloqueos'])
                        m_data['df'] = df_new; m_data['rt'] = rt_new
            guardar_datos(supabase)
        else:
            st.session_state.meses_data = {}
            curr_f = datetime(AÑO_INICIO, MES_INICIO, 1)
            for _ in range(6):
                id_m = f"{curr_f.year}-{curr_f.month:02d}"
                df_ini, rt_ini = generar_calendario_mensual(curr_f.year, curr_f.month, {})
                st.session_state.meses_data[id_m] = {'df': df_ini, 'rt': rt_ini, 'bloqueos': {}, 'fijado': False, 'año': curr_f.year, 'mes': curr_f.month}
                curr_f = (curr_f.replace(day=28) + timedelta(days=4)).replace(day=1)
            guardar_datos(supabase)

    st.markdown("""<style>
        .t-header { font-size: 12px; font-weight: bold; margin-bottom: 4px; text-align: center; }
        .d-header { font-size: 15px; font-weight: bold; margin-bottom: 0px; text-align: center; color: #212529; }
        .legend-text { font-size: 12px; margin-bottom: 4px; padding: 2px 5px; border-radius: 3px; }
    </style>""", unsafe_allow_html=True)

    with st.expander("⚙️ Panel de Control - Gestión de Salas", expanded=False):
        if es_admin and st.button("⚠️ Limpiar y Resetear Todo", key="salas_reset_todo"):
            if borrar_todo_supabase(supabase):
                del st.session_state['meses_data']
                st.rerun()

        st.subheader("👥 Duplas Profesionales")
        for id_dupla, nombre in NOMBRES_DUPLAS.items():
            dias_tt = [dia for dia, lista in TELETRABAJO.items() if id_dupla in lista]
            tt_str = f" (TT: {', '.join(dias_tt)})" if dias_tt else ""
            st.markdown(f"<div class='legend-text' style='color: {COLORES_DUPLAS[id_dupla]}; border-left: 4px solid {COLORES_DUPLAS[id_dupla]};'><b>{id_dupla}:</b> {nombre}{tt_str}</div>", unsafe_allow_html=True)

        st.markdown("---")
        mes_sel = st.selectbox("📅 Seleccionar Mes:", options=list(st.session_state.meses_data.keys()), key="salas_mes_sel")
        m_data = st.session_state.meses_data[mes_sel]
        fijado_check = st.checkbox("🔒 Fijar Mes (Bloquear cambios)", value=m_data['fijado'], key="salas_fijado")
        if fijado_check != m_data['fijado']:
            st.session_state.meses_data[mes_sel]['fijado'] = fijado_check
            guardar_datos(supabase)
            st.rerun()
        foco_duplas = st.multiselect("🔎 Modo Enfoque:", options=DUPLAS, default=[], key="salas_foco")

        if es_admin:
            st.markdown("---")
            st.subheader("📂 Importar Planificación")
            uploaded_file = st.file_uploader("Subir Excel/CSV para este mes:", type=["xlsx", "csv"], key="salas_upload")
            if uploaded_file:
                try:
                    if uploaded_file.name.endswith("xlsx"):
                        new_df = pd.read_excel(uploaded_file)
                    else:
                        new_df = pd.read_csv(uploaded_file)
                    st.session_state.meses_data[mes_sel]['df'] = new_df
                    guardar_datos(supabase)
                    st.success("✅ Datos cargados correctamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al cargar: {e}")

            st.markdown("---")
            if not m_data['fijado']:
                st.subheader("🚫 Bloquear Rango")
                dias_op = [d["fecha_str"] for d in obtener_dias_mes(m_data['año'], m_data['mes'])]
                f_blq = st.selectbox("Fecha:", dias_op, key="salas_bloq_fecha")
                col1, col2 = st.columns(2)
                b_inicio = col1.selectbox("Desde:", BLOQUES, key="salas_bloq_desde")
                b_fin = col2.selectbox("Hasta:", BLOQUES, index=len(BLOQUES)-1, key="salas_bloq_hasta")
                m_blq = st.text_input("Motivo:", key="salas_bloq_motivo").upper()
                if st.button("➕ Aplicar Bloqueo", key="salas_bloq_aplicar"):
                    idx_i = BLOQUES.index(b_inicio); idx_f = BLOQUES.index(b_fin)
                    if idx_i <= idx_f:
                        st.session_state.meses_data[mes_sel]['bloqueos'][f_blq] = {'bloques': BLOQUES[idx_i : idx_f + 1], 'motivo': m_blq}
                        df, rt = generar_calendario_mensual(m_data['año'], m_data['mes'], st.session_state.meses_data[mes_sel]['bloqueos'])
                        st.session_state.meses_data[mes_sel]['df'] = df
                        guardar_datos(supabase)
                        st.rerun()
                if st.button("🔄 Re-generar Planificación", key="salas_regenerar"):
                    st.session_state.meses_data[mes_sel]['bloqueos'] = {}
                    df, rt = generar_calendario_mensual(m_data['año'], m_data['mes'], {})
                    st.session_state.meses_data[mes_sel]['df'] = df
                    st.session_state.meses_data[mes_sel]['rt'] = rt
                    guardar_datos(supabase)
                    st.rerun()

                st.markdown("---")
                st.subheader("🛠️ Editor Manual")
                df_edit = m_data['df']
                edit_fecha = st.selectbox("Día:", df_edit["Fecha"].unique(), key="salas_edit_fecha")
                edit_bloque = st.selectbox("Bloque:", BLOQUES, key="salas_edit_bloque")
                edit_sala = st.selectbox("Sala:", SALAS, key="salas_edit_sala")
                nueva_asig = st.selectbox("Dupla:", DUPLAS + ["---", "L"], key="salas_edit_dupla")
                if st.button("💾 Aplicar Cambio Manual", key="salas_edit_aplicar"):
                    idx = df_edit[(df_edit["Fecha"] == edit_fecha) & (df_edit["Bloque"] == edit_bloque) & (df_edit["Ubicación"] == edit_sala)].index
                    if not idx.empty:
                        st.session_state.meses_data[mes_sel]['df'].at[idx[0], "Dupla"] = nueva_asig
                        guardar_datos(supabase)
                        st.rerun()

                st.markdown("---")
                st.subheader("🚜 Editor de Terrenos")
                edit_t_fecha = st.selectbox("Día Terreno:", df_edit["Fecha"].unique(), key="salas_edit_t_fecha")
                nuevo_t = st.selectbox("Dupla Terreno:", DUPLAS + ["T Disp"], key="salas_edit_t_dupla")
                if st.button("💾 Cambiar Terreno", key="salas_edit_t_aplicar"):
                    st.session_state.meses_data[mes_sel]['df'].loc[st.session_state.meses_data[mes_sel]['df']["Fecha"] == edit_t_fecha, "T_Diario"] = nuevo_t
                    guardar_datos(supabase)
                    st.rerun()

        st.markdown("---")
        excel_data = exportar_excel_visual(m_data['df'], m_data['bloqueos'])
        st.download_button(label="📥 Descargar Excel Visual", data=excel_data, file_name=f"calendario_visual_{mes_sel}.xlsx", key="salas_dl_excel")

        template_buffer = BytesIO()
        with pd.ExcelWriter(template_buffer, engine='xlsxwriter') as writer:
            m_data['df'].to_excel(writer, index=False, sheet_name='Plantilla')
        st.download_button(label="📥 Descargar Plantilla para Importar (Excel)", data=template_buffer.getvalue(), file_name=f"plantilla_importar_{mes_sel}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="salas_dl_plantilla")

        if ICAL_DISPONIBLE:
            ics_data = exportar_icalendar(m_data['df'], m_data['año'], m_data['mes'])
            st.download_button(label="📅 Descargar para Google Calendar", data=ics_data, file_name=f"calendario_{mes_sel}.ics", mime="text/calendar", key="salas_dl_ics")

    # --- Vista del calendario (disponible para todos) ---
    st.markdown(render_resumen_mensual(m_data['df'], foco_duplas), unsafe_allow_html=True)
    mostrar_grafico_comparativo(m_data['df'], foco_duplas)

    df_f = m_data['df']
    semanas = df_f["Semana"].unique()
    for sem in semanas:
        st.subheader(f"Semana {list(semanas).index(sem) + 1}")
        df_sem = df_f[df_f["Semana"] == sem]
        cols = st.columns(5)
        fechas_sem = df_sem["Fecha"].unique()
        for i in range(5):
            dia_n = DIAS_NOMBRE[i]
            f_act = [f for f in fechas_sem if f.startswith(dia_n)]
            if f_act:
                cur_f = f_act[0]
                t_asig = df_sem[df_sem["Fecha"] == cur_f]["T_Diario"].iloc[0]
                with cols[i]:
                    st.markdown(f"<p class='d-header'>{cur_f}</p>", unsafe_allow_html=True)
                    if t_asig in ["T Disp", "CERRADO"]:
                        label_t = "Disponible"
                    else:
                        label_t = f"{t_asig}({obtener_iniciales(t_asig)})"
                    st.markdown(f"<p class='t-header' style='color:{COLORES_DUPLAS.get(t_asig, '#757575')}'>T: {label_t}</p>", unsafe_allow_html=True)
                    st.markdown(render_tabla_dia(df_sem[df_sem["Fecha"] == cur_f], cur_f, m_data['bloqueos'], foco_duplas), unsafe_allow_html=True)
        st.markdown(render_resumen_semanal(df_sem, foco_duplas), unsafe_allow_html=True)
