"""
Módulo Lista de Espera - FAE DEM Cerrillos
==========================================
Reúne todo lo relacionado con la lista de espera, que antes estaba repartido en app.py:

  - cargar_lista_espera(supabase)            -> lee la tabla 'lista_espera' (también la usa el Buscador Rápido).
  - render_carga_lista_espera(supabase, ...) -> bloque de la barra lateral para subir el Excel del SIS.
  - render_lista_espera(supabase, ...)       -> contenido completo de la pestaña "Lista de Espera".

Uso desde app.py:
    from lista_espera import cargar_lista_espera, render_carga_lista_espera, render_lista_espera
"""
import unicodedata
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

# Colores institucionales (mismos valores que en app.py)
COLOR_VERDE_IRIDEM = "#A6CE39"
COLOR_GRIS_FONDO = "#F8F9F9"

# Columnas que se toman del reporte SIS "Reporte_ListaEspera" (el resto se ignora)
COLS_LE = ["CodNino", "Nombres", "Apellido_Paterno", "Apellido_Materno", "FechaNacimiento",
           "Rut", "FechaIngresoLE", "Tribunal", "RIT", "FechaOrden", "ComunaNiño_a"]

COLS_ACCIONES = ["visita_domiciliaria", "entrevista_inicial", "cumple_perfil",
                 "no_cumple_perfil", "ficha_ingreso_completada"]
ETIQUETAS_ACCIONES = {
    "visita_domiciliaria": "Visita domiciliaria",
    "entrevista_inicial": "Entrevista inicial",
    "cumple_perfil": "Cumple perfil",
    "no_cumple_perfil": "No cumple perfil",
    "ficha_ingreso_completada": "Ficha de ingreso completada",
}

DUPLAS_IDS = [f"Dupla {i}" for i in range(1, 8)]


# ==============================================================================
# DATOS
# ==============================================================================
def cargar_lista_espera(supabase):
    """Lee la tabla 'lista_espera' y normaliza fechas y CodNino."""
    try:
        response = supabase.table("lista_espera").select("*").execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['FechaNacimiento'] = pd.to_datetime(df['FechaNacimiento'], errors='coerce').dt.date
            df['FechaIngresoLE'] = pd.to_datetime(df['FechaIngresoLE'], errors='coerce').dt.date
            if 'CodNino' in df.columns:
                df['CodNino'] = pd.to_numeric(df['CodNino'], errors='coerce').astype('Int64')
        return df
    except Exception:
        return pd.DataFrame()


def _norm_col(c):
    """Normaliza un encabezado (minúsculas, sin tildes ni ñ) para encontrarlo aunque cambie un poco."""
    t = unicodedata.normalize('NFD', str(c).strip().lower())
    return ''.join(ch for ch in t if unicodedata.category(ch) != 'Mn')


def preparar_lista_espera(df_raw):
    """Toma el Excel del reporte SIS y devuelve (registros_listos, columnas_faltantes, n_egresados)."""
    norm = {_norm_col(c): c for c in df_raw.columns}
    df = pd.DataFrame(index=df_raw.index)
    faltantes = []
    for col in COLS_LE:
        origen = norm.get(_norm_col(col))
        if origen is None:
            faltantes.append(col)
        else:
            df[col] = df_raw[origen]

    # Si el niño ya tiene fecha de egreso (distinta de 1900-01-01), ya no está en espera
    n_egresados = 0
    c_egreso = norm.get("fechaegresole")
    if c_egreso:
        egreso = pd.to_datetime(df_raw[c_egreso], errors="coerce")
        sigue = egreso.isna() | (egreso.dt.year <= 1900)
        n_egresados = int((~sigue).sum())
        df = df[sigue]

    # Nombres: el SIS trae mezcla de MAYÚSCULAS y minúsculas -> se dejan como "Nombre Apellido"
    for col in ["Nombres", "Apellido_Paterno", "Apellido_Materno"]:
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: str(v).strip().title() if pd.notnull(v) and str(v).strip() not in ("", "0", "0.0") else None
            )
    for col in ["Rut", "RIT", "Tribunal", "ComunaNiño_a"]:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: str(v).strip() if pd.notnull(v) and str(v).strip() else None)

    # Fechas: se quita la hora y las fechas "1900-01-01" (vacías en el SIS) quedan en blanco
    for col in ["FechaNacimiento", "FechaIngresoLE", "FechaOrden"]:
        if col in df.columns:
            f = pd.to_datetime(df[col], errors="coerce")
            f = f.where(f.dt.year > 1900)
            df[col] = f.dt.date
    if "CodNino" in df.columns:
        df["CodNino"] = pd.to_numeric(df["CodNino"], errors="coerce")

    registros = []
    for _, fila in df.iterrows():
        r = {}
        for k, v in fila.items():
            if pd.isnull(v):
                r[k] = None
            elif k == "CodNino":
                r[k] = int(v)
            elif hasattr(v, "isoformat"):
                r[k] = v.isoformat()[:10]
            else:
                r[k] = v
        registros.append(r)
    return registros, faltantes, n_egresados


def planificar_lista_espera(supabase, registros):
    """Compara el Excel con lo que ya hay en Supabase. Devuelve (nuevos, a_actualizar, salen)."""
    existentes = supabase.table("lista_espera").select("*").execute().data or []
    por_cod = {str(e["CodNino"]): e for e in existentes if e.get("CodNino") is not None}
    por_rut = {str(e["Rut"]).strip().upper(): e for e in existentes if e.get("Rut")}
    nuevos, a_actualizar, vistos = [], [], set()
    for r in registros:
        e = None
        if r.get("CodNino") is not None:
            e = por_cod.get(str(r["CodNino"]))
        if e is None and r.get("Rut"):
            e = por_rut.get(str(r["Rut"]).strip().upper())
        if e is not None and e["id"] not in vistos:
            vistos.add(e["id"])
            a_actualizar.append((e["id"], r))
        else:
            nuevos.append(r)
    salen = [e for e in existentes if e["id"] not in vistos]
    return nuevos, a_actualizar, salen


# ==============================================================================
# BARRA LATERAL: CARGA DEL EXCEL DEL SIS
# ==============================================================================
def render_carga_lista_espera(supabase, es_admin=True):
    """Expander de la barra lateral para subir el reporte 'Reporte_ListaEspera' del SIS."""
    etiqueta = "7. ⏳ Cargar Lista de Espera" if es_admin else "⏳ Cargar Lista de Espera"
    with st.sidebar.expander(etiqueta, expanded=False):
        st.caption("Sube el reporte 'Reporte_ListaEspera' descargado del SIS. Los checks de 'Acciones realizadas' de los niños que siguen en la lista se conservan.")
        archivo_espera = st.file_uploader("Subir Excel Lista Espera", type=["xlsx"], key="carga_lista_espera")
        if archivo_espera:
            try:
                df_espera_raw = pd.read_excel(archivo_espera)
                registros_le, cols_faltantes_le, n_egresados_le = preparar_lista_espera(df_espera_raw)

                if cols_faltantes_le:
                    st.warning(f"⚠️ Columnas no encontradas en el Excel (se omiten): {', '.join(cols_faltantes_le)}")
                if n_egresados_le:
                    st.info(f"ℹ️ {n_egresados_le} fila(s) con fecha de egreso se ignoraron (ya no están en espera).")

                if not registros_le:
                    st.error("El Excel no tiene filas válidas para cargar.")
                else:
                    nuevos_le, actualizar_le, salen_le = planificar_lista_espera(supabase, registros_le)
                    st.markdown(f"**Resumen:** 🆕 {len(nuevos_le)} nuevos · 🔄 {len(actualizar_le)} se actualizan · 🚪 {len(salen_le)} salen de la lista")
                    if salen_le:
                        nombres_salen = [f"{s.get('Nombres', '')} {s.get('Apellido_Paterno', '')}".strip() for s in salen_le]
                        st.caption("Salen (ya no aparecen en el Excel): " + ", ".join(nombres_salen))

                    if st.button("🔄 Actualizar Lista de Espera"):
                        if nuevos_le:
                            supabase.table("lista_espera").insert(nuevos_le).execute()
                        for id_reg, datos in actualizar_le:
                            supabase.table("lista_espera").update(datos).eq("id", id_reg).execute()
                        for s in salen_le:
                            supabase.table("lista_espera").delete().eq("id", s["id"]).execute()
                        st.success("Lista de espera actualizada en la nube.")
                        st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")


# ==============================================================================
# PESTAÑA "LISTA DE ESPERA": SECCIONES
# ==============================================================================
def _render_casos_por_dupla(df_c, duplas_nombres):
    st.subheader("👥 Casos Activos por Dupla")
    st.caption("Referencia para decidir a quién asignar el próximo ingreso.")

    data_conteo = []
    for d_id in DUPLAS_IDS:
        integrantes_dupla = duplas_nombres.get(d_id, "")
        cant = len(df_c[df_c['Dupla_ID_Asignada'] == d_id])
        data_conteo.append({"Dupla_Label": f"{d_id}\n({integrantes_dupla})", "Casos Activos": cant})

    df_conteo = pd.DataFrame(data_conteo)
    fig = px.bar(df_conteo, x='Dupla_Label', y='Casos Activos', text='Casos Activos',
                 color_discrete_sequence=[COLOR_VERDE_IRIDEM])
    max_casos = df_conteo['Casos Activos'].max() if not df_conteo.empty else 10
    fig.update_traces(textposition='outside', textfont_size=11, width=0.4)
    fig.update_layout(
        xaxis_tickangle=-25, height=280, paper_bgcolor=COLOR_GRIS_FONDO, plot_bgcolor=COLOR_GRIS_FONDO,
        yaxis_title="N° de Casos", xaxis_title="",
        yaxis=dict(range=[0, max_casos * 1.25]),
        margin=dict(t=30, b=80)
    )
    col_graf, _ = st.columns([1, 1])
    with col_graf:
        st.plotly_chart(fig, use_container_width=True, key="grafico_casos_por_dupla")


def _render_ingresos_por_mes(df_c, duplas_nombres, hoy):
    st.subheader("📅 Casos Ingresados por Mes (último año)")
    st.caption("Cantidad de casos que ingresaron al programa cada mes. Elige un mes en la lista o haz clic en su barra para ver los casos.")

    nombres_mes_corto = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    periodo_hoy = pd.Period(hoy, freq="M")
    meses_rango = [periodo_hoy - i for i in range(11, -1, -1)]
    etiqueta_por_periodo = {p: f"{nombres_mes_corto[p.month - 1]} {p.year}" for p in meses_rango}
    periodo_por_etiqueta = {v: k for k, v in etiqueta_por_periodo.items()}

    periodos_ingreso = pd.to_datetime(df_c['Fecha Ingreso']).dt.to_period("M")
    ingresos_por_mes = periodos_ingreso.value_counts()
    df_ingresos_mes = pd.DataFrame([
        {"Mes": etiqueta_por_periodo[p], "Casos ingresados": int(ingresos_por_mes.get(p, 0))}
        for p in meses_rango
    ])
    total_ingresos_12m = int(df_ingresos_mes["Casos ingresados"].sum())
    st.info(f"En los últimos 12 meses ingresaron **{total_ingresos_12m}** caso(s) al programa.")

    # Mes seleccionado (por defecto, el mes actual)
    if st.session_state.get("sel_mes_ingreso") not in periodo_por_etiqueta:
        st.session_state["sel_mes_ingreso"] = etiqueta_por_periodo[periodo_hoy]

    col_graf_ingresos, col_lista_ingresos = st.columns([1, 1])
    with col_graf_ingresos:
        fig = px.bar(df_ingresos_mes, x="Mes", y="Casos ingresados", text="Casos ingresados",
                     color_discrete_sequence=[COLOR_VERDE_IRIDEM])
        max_ing = max(int(df_ingresos_mes["Casos ingresados"].max()), 1)
        fig.update_traces(textposition="outside", textfont_size=11, width=0.5)
        fig.update_xaxes(categoryorder="array", categoryarray=df_ingresos_mes["Mes"].tolist())
        fig.update_layout(
            height=280, paper_bgcolor=COLOR_GRIS_FONDO, plot_bgcolor=COLOR_GRIS_FONDO,
            xaxis_title="", yaxis_title="N° de casos", xaxis_tickangle=-45,
            yaxis=dict(range=[0, max_ing * 1.25], dtick=1 if max_ing <= 10 else None),
            margin=dict(t=30, b=80)
        )
        evento_mes = st.plotly_chart(fig, use_container_width=True, on_select="rerun", key="grafico_ingresos_mes")
        if evento_mes and evento_mes.selection and len(evento_mes.selection.points) > 0:
            mes_clic = evento_mes.selection.points[0]['x']
            # Solo se aplica un clic nuevo, para que la lista desplegable también pueda cambiar el mes.
            if mes_clic in periodo_por_etiqueta and mes_clic != st.session_state.get("_ultimo_clic_mes_ingreso"):
                st.session_state["_ultimo_clic_mes_ingreso"] = mes_clic
                st.session_state["sel_mes_ingreso"] = mes_clic
        else:
            st.session_state["_ultimo_clic_mes_ingreso"] = None

    with col_lista_ingresos:
        opciones_meses = [etiqueta_por_periodo[p] for p in reversed(meses_rango)]
        mes_elegido = st.selectbox("Mes de ingreso:", opciones_meses, key="sel_mes_ingreso")
        df_mes = df_c[periodos_ingreso == periodo_por_etiqueta[mes_elegido]].copy()

        if df_mes.empty:
            st.info(f"No ingresaron casos en {mes_elegido}.")
        else:
            df_mes['Dupla'] = df_mes['Dupla_ID_Asignada'].apply(
                lambda d: f"{d} ({duplas_nombres.get(d, '')})" if d in duplas_nombres else str(d)
            )
            df_mes = df_mes.sort_values(['Fecha Ingreso', 'Caso']).reset_index(drop=True)
            df_mes['Fecha Ingreso'] = df_mes['Fecha Ingreso'].apply(lambda f: f.strftime('%d-%m-%Y'))
            df_mes.insert(0, "N°", range(1, len(df_mes) + 1))
            columnas_mes = [c for c in ["N°", "Caso", "RIT", "codnino", "Dupla", "Fecha Ingreso"] if c in df_mes.columns]
            st.markdown(f"**{len(df_mes)} caso(s) ingresado(s) en {mes_elegido}**")
            st.dataframe(df_mes[columnas_mes], use_container_width=True, hide_index=True)


def _render_tabla_lista_espera(supabase, df_le, total_casos_programa, hoy):
    """Tabla editable con las 'Acciones realizadas' + eliminación de registros."""
    st.subheader("⏳ Casos en Lista de Espera")
    msg_eliminados = st.session_state.pop("msg_le_eliminados", None)
    if msg_eliminados:
        st.success(msg_eliminados)

    if df_le.empty:
        st.success("No hay casos en lista de espera.")
        return

    df_le['Días en Lista de Espera'] = df_le['FechaIngresoLE'].apply(
        lambda f: (hoy - f).days if pd.notnull(f) else None
    )

    def _calcular_edad_le(f_nac):
        if pd.isnull(f_nac):
            return None
        return hoy.year - f_nac.year - ((hoy.month, hoy.day) < (f_nac.month, f_nac.day))

    if 'FechaNacimiento' in df_le.columns:
        df_le['Edad'] = df_le['FechaNacimiento'].apply(_calcular_edad_le)

    cols_le = list(df_le.columns)
    if 'FechaIngresoLE' in cols_le and 'Días en Lista de Espera' in cols_le:
        cols_le.remove('Días en Lista de Espera')
        cols_le.insert(cols_le.index('FechaIngresoLE') + 1, 'Días en Lista de Espera')
    if 'FechaNacimiento' in cols_le and 'Edad' in cols_le:
        cols_le.remove('Edad')
        cols_le.insert(cols_le.index('FechaNacimiento') + 1, 'Edad')
    df_le = df_le[cols_le]

    # Orden de la lista: quien lleva MÁS días en espera va primero (N° 1) y el ingreso más reciente al final.
    # Si dos niños/as llevan los mismos días, se desempata por 'id' (el que se cargó antes va primero).
    # Los que no tienen fecha de ingreso a la lista quedan al final.
    df_le['_dias_orden'] = pd.to_numeric(df_le['Días en Lista de Espera'], errors='coerce')
    columnas_orden = ['_dias_orden'] + (['id'] if 'id' in df_le.columns else [])
    df_le = (
        df_le.sort_values(columnas_orden, ascending=[False] + [True] * (len(columnas_orden) - 1), na_position='last')
        .drop(columns=['_dias_orden'])
        .reset_index(drop=True)
    )

    # N° correlativo (siempre de 1 a N). El id real sigue existiendo pero se oculta más abajo.
    df_le.insert(0, "N°", range(1, len(df_le) + 1))

    for col_acc in COLS_ACCIONES:
        if col_acc not in df_le.columns:
            df_le[col_acc] = False
        else:
            df_le[col_acc] = df_le[col_acc].fillna(False)

    st.info(f"Actualmente hay **{len(df_le)}** niños/as en lista de espera y **{total_casos_programa}** casos activos en el programa.")

    col_config = {c: st.column_config.CheckboxColumn(ETIQUETAS_ACCIONES[c]) for c in COLS_ACCIONES}
    col_config["id"] = None  # oculta el id en pantalla
    cols_no_editables = [c for c in df_le.columns if c not in COLS_ACCIONES and c != 'id']

    df_le_editado = st.data_editor(
        df_le, use_container_width=True, hide_index=True,
        column_config=col_config,
        disabled=cols_no_editables + (['id'] if 'id' in df_le.columns else []),
        key="editor_lista_espera"
    )

    if st.button("💾 Guardar Cambios en Acciones Realizadas"):
        if 'id' not in df_le.columns:
            st.error("No se puede guardar: falta la columna 'id' en la tabla.")
        else:
            cambios = 0
            for idx in df_le.index:
                fila_original = df_le.loc[idx]
                fila_nueva = df_le_editado.loc[idx]
                diffs = {c: bool(fila_nueva[c]) for c in COLS_ACCIONES if bool(fila_original[c]) != bool(fila_nueva[c])}
                if diffs:
                    try:
                        supabase.table("lista_espera").update(diffs).eq("id", fila_original['id']).execute()
                        cambios += 1
                    except Exception:
                        pass
            if cambios:
                st.success(f"✅ {cambios} registro(s) actualizado(s).")
                st.rerun()

    # --- Eliminar de la lista de espera (el N° correlativo se recalcula solo al recargar) ---
    st.divider()
    st.subheader("🗑️ Eliminar de la Lista de Espera")
    if 'id' in df_le.columns:
        opciones_eliminar = {}
        for _, r_del in df_le.iterrows():
            partes_nombre = [str(r_del.get(k)).strip() for k in ["Nombres", "Apellido_Paterno", "Apellido_Materno"]
                             if pd.notnull(r_del.get(k)) and str(r_del.get(k)).strip()]
            nombre_del = " ".join(partes_nombre) if partes_nombre else "Sin nombre"
            rit_del = str(r_del.get('RIT')) if pd.notnull(r_del.get('RIT')) else "S/R"
            opciones_eliminar[f"N° {r_del['N°']} - {nombre_del} - RIT {rit_del}"] = int(r_del['id'])

        with st.form("form_eliminar_le", clear_on_submit=True):
            sel_eliminar = st.multiselect("Selecciona uno o más niños/as a eliminar", list(opciones_eliminar.keys()))
            confirmar_eliminar = st.checkbox("Confirmo que quiero eliminarlos de la lista de espera")
            enviar_eliminar = st.form_submit_button("🗑️ Eliminar seleccionados")

        if enviar_eliminar:
            if not sel_eliminar:
                st.warning("Selecciona al menos un registro.")
            elif not confirmar_eliminar:
                st.warning("Marca la casilla de confirmación para poder eliminar.")
            else:
                eliminados, errores = 0, []
                for etiqueta_del in sel_eliminar:
                    try:
                        supabase.table("lista_espera").delete().eq("id", opciones_eliminar[etiqueta_del]).execute()
                        eliminados += 1
                    except Exception as e:
                        errores.append(f"{etiqueta_del}: {e}")
                for err in errores:
                    st.error(f"❌ No se pudo eliminar {err}")
                if eliminados:
                    st.session_state.pop("editor_lista_espera", None)  # evita arrastrar ediciones de filas que ya no existen
                    st.session_state["msg_le_eliminados"] = f"✅ {eliminados} registro(s) eliminado(s). El orden (N°) se actualizó."
                    st.rerun()
        st.caption("Si el niño/a sigue apareciendo en el Excel del SIS, volverá a ingresar a la lista en la próxima carga.")


def _render_registrar_desde_espera(supabase, df_le_reg, duplas_nombres):
    """Convierte a una persona de la lista de espera en caso activo (y la quita de la lista)."""
    st.subheader("➕ Registrar Caso desde Lista de Espera")
    if df_le_reg.empty:
        st.caption("No hay personas en la Lista de Espera para registrar como caso.")
        return

    opciones_le = {}
    for idx, r in df_le_reg.iterrows():
        nombre_completo = f"{r.get('Nombres', '')} {r.get('Apellido_Paterno', '')} {r.get('Apellido_Materno', '')}".strip()
        rit_ref = r.get('RIT', 'S/R') if pd.notnull(r.get('RIT')) else "S/R"
        opciones_le[f"{nombre_completo} - RIT {rit_ref}"] = idx

    seleccion_le = st.selectbox("Selecciona a la persona de la Lista de Espera", ["---"] + list(opciones_le.keys()), key="sel_le_a_caso")
    if seleccion_le == "---":
        return

    fila_le = df_le_reg.loc[opciones_le[seleccion_le]]
    nombre_sugerido = f"{fila_le.get('Nombres', '')} {fila_le.get('Apellido_Paterno', '')} {fila_le.get('Apellido_Materno', '')}".strip()
    rit_sugerido = str(fila_le.get('RIT', '')) if pd.notnull(fila_le.get('RIT')) else ""
    fecnac_le = fila_le.get('FechaNacimiento')
    fecnac_sugerida = fecnac_le if pd.notnull(fecnac_le) else datetime.now()
    cod_le = fila_le.get('CodNino')
    codnino_sugerido = str(int(cod_le)) if cod_le is not None and pd.notnull(cod_le) else ""

    with st.form("form_le_a_caso"):
        caso_nombre_nuevo = st.text_input("Nombre del Caso", nombre_sugerido)
        rit_nuevo = st.text_input("Causa RIT", rit_sugerido)
        codnino_nuevo = st.text_input("Cod. Niño", codnino_sugerido)
        fecnac_nuevo = st.date_input("Fecha de Nacimiento", fecnac_sugerida, min_value=datetime(1990, 1, 1))

        opciones_duplas_le = [f"{d}: {duplas_nombres.get(d, '')}" for d in DUPLAS_IDS]
        prof_elegido_le = st.selectbox("Asignar Dupla", opciones_duplas_le, key="prof_le_a_caso")
        # Se guarda el ID estable de la dupla, no el nombre resuelto de integrantes.
        prof_nuevo = prof_elegido_le.split(":")[0].strip()

        f_ing_nuevo = st.date_input("Fecha Ingreso", datetime.now(), key="fing_le_a_caso")

        if st.form_submit_button("✅ Registrar como Caso y eliminar de Lista de Espera") and caso_nombre_nuevo:
            try:
                tribunal_le = fila_le.get('Tribunal')
                comuna_le = fila_le.get('ComunaNiño_a')
                nuevo_caso = {
                    "Caso": str(caso_nombre_nuevo).strip(), "RIT": str(rit_nuevo).strip(),
                    "codnino": str(codnino_nuevo).strip(), "fechanacimiento": str(fecnac_nuevo),
                    "Profesional": prof_nuevo, "Fecha Ingreso": str(f_ing_nuevo),
                    "Tribunal": str(tribunal_le).strip() if pd.notnull(tribunal_le) else "S/I",
                    "Comuna": str(comuna_le).strip() if pd.notnull(comuna_le) else "S/I",
                }
                supabase.table("casos").insert(nuevo_caso).execute()

                if 'id' in fila_le.index and pd.notnull(fila_le.get('id')):
                    supabase.table("lista_espera").delete().eq("id", int(fila_le['id'])).execute()
                else:
                    supabase.table("lista_espera").delete().match({
                        "Nombres": fila_le.get('Nombres'), "Apellido_Paterno": fila_le.get('Apellido_Paterno'),
                        "Apellido_Materno": fila_le.get('Apellido_Materno'),
                    }).execute()

                st.success(f"✅ Caso '{caso_nombre_nuevo}' registrado y eliminado de la Lista de Espera")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al registrar: {e}")


# ==============================================================================
# PESTAÑA "LISTA DE ESPERA": PUNTO DE ENTRADA
# ==============================================================================
def render_lista_espera(supabase, df_c, duplas_nombres, hoy):
    """
    Dibuja toda la pestaña de Lista de Espera.
      supabase       : cliente de Supabase
      df_c           : DataFrame de casos activos (debe incluir la columna 'Dupla_ID_Asignada')
      duplas_nombres : dict {"Dupla 1": "Integrantes...", ...}
      hoy            : fecha de hoy (datetime.date)
    """
    total_casos_programa = len(df_c)
    df_le_base = cargar_lista_espera(supabase)  # se lee una sola vez por ejecución
    total_en_espera = len(df_le_base)

    col_t1, col_t2, col_t3 = st.columns(3)
    col_t1.metric("📁 Total de casos en el programa", total_casos_programa)
    col_t2.metric("⏳ Niños/as en lista de espera", total_en_espera)
    col_t3.metric("👥 Total general (programa + espera)", total_casos_programa + total_en_espera)

    st.divider()
    _render_casos_por_dupla(df_c, duplas_nombres)

    st.divider()
    _render_ingresos_por_mes(df_c, duplas_nombres, hoy)

    st.divider()
    _render_tabla_lista_espera(supabase, df_le_base.copy(), total_casos_programa, hoy)

    st.divider()
    _render_registrar_desde_espera(supabase, df_le_base.copy(), duplas_nombres)
