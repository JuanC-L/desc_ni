import streamlit as st
import pandas as pd
import re
from rapidfuzz import process, fuzz
import io

# ==========================================
# 1. CONFIGURACIÓN VISUAL
# ==========================================
st.set_page_config(page_title="Recordando NLP", layout="wide")

# CSS para limpiar la vista
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .block-container {padding-top: 2rem;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. FUNCIONES DE LÓGICA (TU CÓDIGO + FIX SEMANA)
# ==========================================

def limpiar(texto):
    if not isinstance(texto, str): return ""
    texto = re.sub(r'\b(s\.?a\.?c\.?|s\.?a\.?|e\.?i\.?r\.?l\.?|s\.?r\.?l\.?|ltda)\b', '', texto.lower().strip())
    texto = re.sub(r'[^a-z0-9\sñ]', '', texto)
    return re.sub(r'\s+', ' ', texto).strip()

def obtener_catalogo_ordenado(lista_sucia):
    lista_limpia = [str(i).strip() for i in lista_sucia if pd.notna(i) and str(i).strip() != ""]
    return sorted(list(set(lista_limpia)), key=len, reverse=True)

# --- MOTORES DE BÚSQUEDA ---

def escanear_entidad(texto, catalogo, umbral=85):
    mejor_match = None
    for item in catalogo:
        # Match exacto para cortos
        if len(item) <= 3:
            patron = r'\b' + re.escape(item.lower()) + r'\b'
            if re.search(patron, texto):
                mejor_match = item
                texto = re.sub(patron, ' ', texto) 
                break 
        # Match fuzzy para largos
        else:
            score = fuzz.partial_ratio(item.lower(), texto)
            if score >= umbral:
                mejor_match = item
                # Borrado simple del texto encontrado
                palabras = texto.split()
                nuevas_palabras = []
                for p in palabras:
                    if fuzz.ratio(p, item.lower()) < 80:
                        nuevas_palabras.append(p)
                texto = " ".join(nuevas_palabras)
                break
    return mejor_match, texto

def decodificar_maestro(texto_raw, marcas_db, tipos_db):
    if not isinstance(texto_raw, str): return {}
    
    # 1. LIMPIEZA INICIAL
    texto_trabajo = texto_raw.lower()

    # ---> FIX SEMANA (SOLO ESTO ES NUEVO) <---
    # Borra "Semana 5", "Sem 1", "S. 4" antes de buscar nada más.
    texto_trabajo = re.sub(r'\b(semana|sem|s\.?)\s*\d+', ' ', texto_trabajo)
    
    # Limpieza estándar (Tu código)
    texto_trabajo = re.sub(r'[^a-z0-9\sñ]', ' ', texto_trabajo)
    texto_trabajo = re.sub(r'\s+', ' ', texto_trabajo)
    
    res = {'Accion_Sugerida': 'NEUTRO', 'Cant_Sugerida': None, 'Marca_Sugerida': None, 'Tipo_Sugerido': None}
    
    # 2. EXTRAER MARCA Y TIPO (Tu código)
    res['Marca_Sugerida'], texto_trabajo = escanear_entidad(texto_trabajo, marcas_db)
    res['Tipo_Sugerido'], texto_trabajo = escanear_entidad(texto_trabajo, tipos_db)
    
    # 3. EXTRAER CANTIDAD (Tu código)
    # Como ya borramos "Semana 5" arriba, el primer número que encuentre será el correcto (100)
    numeros = re.findall(r'\b(\d+)\b', texto_trabajo)
    if numeros:
        res['Cant_Sugerida'] = int(numeros[0])
    
    # 4. EXTRAER ACCIÓN (Tu código recuperado)
    acciones_keywords = {
        'RESTAR': ['descontar', 'quitar', 'restar', 'devolver', 'mermar', 'error', 'bajar', 'sacar', 'descantar', 'descuenten', 'diferencia', 'anular'],
        'SUMAR':  ['agregar', 'adicionar', 'sumar', 'aumentar', 'ingresar', 'reposicion', 'boni', 'extra', 'mas']
    }

    palabras_restantes = texto_trabajo.split()
    max_score = 0
    accion_detectada = 'NEUTRO'

    for palabra in palabras_restantes:
        if len(palabra) < 3: continue 
        for accion_tipo, lista_palabras in acciones_keywords.items():
            match, score, _ = process.extractOne(palabra, lista_palabras, scorer=fuzz.ratio)
            
            # ---> PEQUEÑO AJUSTE AQUÍ: Usamos >= en vez de >
            # Esto permite que si aparece "extra" (Sumar) y luego "error" (Restar),
            # la última palabra gane. O si tienen el mismo score, prevalezca la corrección.
            if score > 85 and score >= max_score:
                max_score = score
                accion_detectada = accion_tipo
                
    res['Accion_Sugerida'] = accion_detectada
    return res

def buscar_proveedor(texto, db_prov, claves_prov, alias_db, claves_alias):
    q = limpiar(texto)
    if not q: return None
    
    if claves_alias:
        match_a, score_a, _ = process.extractOne(q, claves_alias, scorer=fuzz.token_sort_ratio)
        if score_a >= 85:
            q = alias_db[match_a] 
            
    match, score, _ = process.extractOne(q, claves_prov, scorer=fuzz.token_set_ratio)
    if score >= 60:
        return db_prov[match]
    return None

# ==========================================
# 3. CARGA DE MAESTROS
# ==========================================
@st.cache_data
def cargar_maestros():
    try:
        df_om = pd.read_excel('base_om.xlsx')
        provs = df_om['Proveedor'].dropna().unique()
        db_prov = {limpiar(p): p for p in provs if len(limpiar(p)) > 0}
        
        try:
            df_a = pd.read_excel('alias_proveedores.xlsx')
            alias_db = dict(zip(df_a['alias'].apply(limpiar), df_a['nombre_real'].apply(limpiar)))
        except: alias_db = {}

        return {
            'prov_set': set(provs),
            'db_prov': db_prov,
            'claves_prov': list(db_prov.keys()),
            'alias_db': alias_db,
            'claves_alias': list(alias_db.keys()),
            'marcas': obtener_catalogo_ordenado(df_om['Marca']),
            'tipos': obtener_catalogo_ordenado(df_om['Tipo'])
        }
    except: return None

maestros = cargar_maestros()

# ==========================================
# 4. INTERFAZ Y PROCESO (CON GESTIÓN DE ALIAS)
# ==========================================

st.title("Recordando NLP")

if not maestros:
    st.error("❌ Error Crítico: Falta 'base_om.xlsx'.")
    st.stop()

# CREAMOS DOS PESTAÑAS
tab_proceso, tab_admin = st.tabs(["Procesar Archivos", "Gestionar Alias"])

# -----------------------------------------------------------------------------
# PESTAÑA 1: EL PROCESO DE SIEMPRE
# -----------------------------------------------------------------------------
with tab_proceso:
    archivo_nuevo = st.file_uploader("Cargar Excel Semanal", type=["xlsx"])

    if archivo_nuevo:
        # Botón primario para procesar
        if st.button("Analizar Datos", type="primary"):
            with st.spinner('Analizando...'):
                df_new = pd.read_excel(archivo_nuevo)
                
                # 1. Lógica Proveedores
                prov_final = []
                for p in df_new['Proveedor']:
                    # Buscamos primero en el set exacto
                    if p in maestros['prov_set']: 
                        prov_final.append(p)
                    else:
                        # Si no, usamos el buscador (que ahora leerá los alias actualizados)
                        sug = buscar_proveedor(str(p), maestros['db_prov'], maestros['claves_prov'], maestros['alias_db'], maestros['claves_alias'])
                        prov_final.append(sug if sug else p)
                df_new['Proveedor_Final'] = prov_final
                
                # 2. Lógica Comentarios
                detalles = df_new['Comentario'].apply(lambda x: decodificar_maestro(str(x), maestros['marcas'], maestros['tipos']))
                df_detalles = pd.json_normalize(detalles)
                
                st.session_state['df_resultado'] = pd.concat([df_new, df_detalles], axis=1)
                st.rerun()

    # RESULTADOS (Igual que antes)
    if 'df_resultado' in st.session_state:
        df = st.session_state['df_resultado']
        st.divider()
        
        # Preparar vista
        cols_vista = ['Proveedor', 'Proveedor_Final', 'Comentario', 'Accion_Sugerida', 'Cant_Sugerida', 'Marca_Sugerida', 'Tipo_Sugerido']
        cols_existentes = [c for c in cols_vista if c in df.columns]
        df_view = df[cols_existentes].copy()
        
        # Ordenar
        df_view['Prioridad'] = df_view['Accion_Sugerida'].map({'RESTAR': 0, 'SUMAR': 1}).fillna(2)
        df_view = df_view.sort_values(by=['Prioridad', 'Proveedor'])
        df_view = df_view.drop(columns=['Prioridad'])

        # Editor
        df_editado_vista = st.data_editor(
            df_view,
            column_config={
                "Accion_Sugerida": st.column_config.SelectboxColumn("Acción", options=["NEUTRO", "SUMAR", "RESTAR"], required=True),
                "Cant_Sugerida": st.column_config.NumberColumn("Cant", format="%d"),
                "Comentario": st.column_config.TextColumn("Original", disabled=True, width="large"),
            },
            use_container_width=True,
            hide_index=True
        )
        
        st.session_state['df_resultado'].update(df_editado_vista)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            st.session_state['df_resultado'].to_excel(writer, index=False, sheet_name='Procesado')
        
        st.download_button("Descargar Excel", buffer.getvalue(), "Reporte_Limpio.xlsx", "application/vnd.ms-excel")

# -----------------------------------------------------------------------------
# PESTAÑA 2: AGREGAR NUEVOS ALIAS (LO NUEVO)
# -----------------------------------------------------------------------------
with tab_admin:
    st.header("Entrenar al Sistema")
    st.markdown("Si el sistema no reconoció un proveedor, agrégalo aquí para que la próxima vez lo detecte automático.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Input del usuario: El nombre "malo"
        nuevo_alias = st.text_input("Escribe el Alias (Nombre Malo/Incompleto)")
    
    with col2:
        # Selectbox: El nombre "bueno" (Sacado de tu Base Maestra)
        # Convertimos el set a lista ordenada para el dropdown
        lista_provs = sorted(list(maestros['prov_set']))
        proveedor_real = st.selectbox("Selecciona el Proveedor Correcto", options=lista_provs)
        
    if st.button("💾 Guardar Nueva Regla"):
        if nuevo_alias and proveedor_real:
            try:
                # 1. Cargar archivo existente o crear uno nuevo
                archivo_alias = 'alias_proveedores.xlsx'
                try:
                    df_actual = pd.read_excel(archivo_alias)
                except FileNotFoundError:
                    df_actual = pd.DataFrame(columns=['alias', 'nombre_real'])
                
                # 2. Crear nueva fila
                nueva_fila = pd.DataFrame({'alias': [nuevo_alias], 'nombre_real': [proveedor_real]})
                
                # 3. Guardar (Concatenar y sobrescribir Excel)
                df_actualizado = pd.concat([df_actual, nueva_fila], ignore_index=True)
                df_actualizado.to_excel(archivo_alias, index=False)
                
                # 4. LIMPIAR CACHÉ Y RECARGAR (CRUCIAL)
                # Esto obliga a Streamlit a releer los excels
                st.cache_data.clear()
                
                st.success(f"✅ Regla guardada: '{nuevo_alias}' ahora es '{proveedor_real}'.")
                st.info("🔄 Recargando sistema...")
                import time
                time.sleep(1)
                st.rerun()
                
            except Exception as e:
                st.error(f"Error al guardar: {e}")
        else:
            st.warning("⚠️ Por favor llena ambos campos.")

    st.divider()
    st.subheader("Base de Conocimiento Actual (Alias)")
    
    # Mostrar tabla actual de alias para referencia
    try:
        df_ver = pd.read_excel('alias_proveedores.xlsx')
        st.dataframe(df_ver, use_container_width=True, hide_index=True)
    except:
        st.info("Aún no hay alias registrados.")