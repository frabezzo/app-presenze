import streamlit as st
import pandas as pd
import google.generativeai as genai
import PIL.Image
import json

st.set_page_config(page_title="Gestione Presenze & Timbrature", layout="wide")

st.title("⏱️ Gestione Presenze & Calcolo Timbrature")
st.write("Carica la foto del cartellino, verifica e completa le timbrature per ottenere il bilancio dei minuti, il riepilogo delle giustificazioni e salvare lo storico mensile.")

# Inizializzazione Registro Storico nella sessione
if 'registro_storico' not in st.session_state:
    st.session_state['registro_storico'] = {}

# Sidebar per la configurazione
st.sidebar.header("Impostazioni")
api_key = st.sidebar.text_input("Inserisci la tua Gemini API Key", type="password")

target_hours = st.sidebar.number_input("Ore turno giornaliero", value=7, min_value=0, max_value=24)
target_minutes = st.sidebar.number_input("Minuti turno giornaliero", value=36, min_value=0, max_value=59)
target_total_min = target_hours * 60 + target_minutes

st.sidebar.markdown("---")
st.sidebar.header("📁 Gestione Storico Mese")
nome_mese = st.sidebar.text_input("Mese e Anno Riferimento", value="Luglio 2026")

uploaded_file = st.file_uploader("Scegli o scatta una foto del cartellino presenze", type=["jpg", "jpeg", "png"])

def time_to_minutes(time_str):
    if not time_str or str(time_str).strip() in ["", "nan", "None", "-"]:
        return None
    try:
        time_str = str(time_str).strip().replace('.', ':').replace(',', ':')
        parts = time_str.split(':')
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return h * 60 + m
    except:
        return None

def minutes_to_hhmm(minutes):
    if minutes is None:
        return ""
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

def clean_json_response(raw_text):
    clean = raw_text.strip()
    if "json" in clean:
        clean = clean.split("json")[-1]
    clean = clean.replace("`", "").strip()
    return clean

if uploaded_file and api_key:
    genai.configure(api_key=api_key)
    image = PIL.Image.open(uploaded_file)
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(image, caption="Foto Cartellino", use_container_width=True)
    
    with col2:
        if st.button("🔍 Analizza Immagine con AI", type="primary"):
            with st.spinner("Estraggo le timbrature dall'immagine..."):
                try:
                    model = genai.GenerativeModel('gemini-3.6-flash')
                    prompt = "Analizza questa tabella di presenze/timbrature. Restituisci unicamente un array JSON di oggetti con chiavi: data, giorno, e1, u1, e2, u2. Se ci sono solo 2 timbrature e la seconda e dopo le 15:00, posizionala su u2 e lascia vuoti u1 ed e2."
                    
                    response = model.generate_content([prompt, image])
                    text_resp = clean_json_response(response.text)
                    data_json = json.loads(text_resp)
                    
                    df_extracted = pd.DataFrame(data_json)
                    st.session_state['df_original'] = df_extracted.copy()
                    st.session_state['df_edited'] = df_extracted.copy()
                    st.success("Estrazione completata! Puoi verificare e modificare i dati qui sotto.")
                except Exception as e:
                    st.error(f"Errore durante l'analisi: {e}")

if 'df_edited' in st.session_state:
    st.subheader("1. Griglia Timbrature Completa (Integrazione Manuale)")
    st.info("💡 Completa le celle vuote dove mancano le timbrature. I calcoli e i report si aggiorneranno automaticamente.")
    
    edited_df = st.data_editor(
        st.session_state['df_edited'],
        column_config={
            "data": "Data",
            "giorno": "Giorno",
            "e1": "Entrata 1",
            "u1": "Uscita 1 (Pranzo)",
            "e2": "Rientro 2 (Pranzo)",
            "u2": "Uscita Finale",
        },
        num_rows="dynamic",
        use_container_width=True
    )
    
    results = []
    only_added_rows = []
    
    for idx, row in edited_df.iterrows():
        e1_m = time_to_minutes(row.get('e1'))
        u1_m = time_to_minutes(row.get('u1'))
        e2_m = time_to_minutes(row.get('e2'))
        u2_m = time_to_minutes(row.get('u2'))
        
        orig_row = st.session_state['df_original'].iloc[idx] if 'df_original' in st.session_state and idx < len(st.session_state['df_original']) else {}
        
        added_dict = {
            "Data": row.get('data'),
            "Giorno": row.get('giorno'),
            "Entrata 1": "",
            "Uscita 1 (Pranzo)": "",
            "Rientro 2 (Pranzo)": "",
            "Uscita Finale": ""
        }
        
        has_added = False
        mapping = [('e1', 'Entrata 1'), ('u1', 'Uscita 1 (Pranzo)'), ('e2', 'Rientro 2 (Pranzo)'), ('u2', 'Uscita Finale')]
        for col_code, col_name in mapping:
            val = str(row.get(col_code, '')).strip()
            orig_val = str(orig_row.get(col_code, '')).strip() if orig_row else ""
            if val and val != orig_val and val not in ["nan", "None"]:
                added_dict[col_name] = val
                has_added = True
                
        if has_added:
            only_added_rows.append(added_dict)
            
        total_m = 0
        if e1_m and u1_m and e2_m and u2_m:
            total_m = (u1_m - e1_m) + (u2_m - e2_m)
        elif e1_m and u2_m:
            total_m = u2_m - e1_m
        
        diff = total_m - target_total_min if total_m > 0 else 0
        
        results.append({
            "Data": row.get('data'),
            "Giorno": row.get('giorno'),
            "Entrata 1": row.get('e1', ''),
            "Uscita 1": row.get('u1', ''),
            "Entrata 2": row.get('e2', ''),
            "Uscita 2": row.get('u2', ''),
            "Ore Lavorate": minutes_to_hhmm(total_m) if total_m > 0 else "-",
            "Variazione (Minuti)": diff if total_m > 0 else 0
        })
        
    res_df = pd.DataFrame(results)
    
    st.subheader("2. Bilancio e Variazioni Giornaliere")
    
    tot_eccesso = res_df[res_df["Variazione (Minuti)"] > 0]["Variazione (Minuti)"].sum()
    tot_difetto = res_df[res_df["Variazione (Minuti)"] < 0]["Variazione (Minuti)"].sum()
    saldo_netto = tot_eccesso + tot_difetto
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Minuti in Eccesso (+)", f"+{tot_eccesso} min ({minutes_to_hhmm(tot_eccesso)})")
    m2.metric("Minuti in Difetto (-)", f"{tot_difetto} min ({minutes_to_hhmm(abs(tot_difetto))})")
    m3.metric("Saldo Netto Mese", f"{saldo_netto} min", delta=f"{saldo_netto} min")
    
    st.dataframe(res_df[["Data", "Giorno", "Ore Lavorate", "Variazione (Minuti)"]], use_container_width=True)
    
    st.subheader("3. Tabella con le SOLE Timbrature Inserite a Mano")
    if only_added_rows:
        added_df = pd.DataFrame(only_added_rows)
        st.dataframe(added_df, use_container_width=True)
    else:
        st.write("Nessuna timbratura inserita manualmente.")

    st.markdown("---")
    if st.button(f"💾 Salva '{nome_mese}' nel Registro Storico", type="primary"):
        st.session_state['registro_storico'][nome_mese] = {
            "totale_df": res_df,
            "soltanmante_inserite_df": pd.DataFrame(only_added_rows) if only_added_rows else pd.DataFrame(),
            "saldo_netto": saldo_netto
        }
        st.success(f"Mese '{nome_mese}' salvato con successo nello storico del Registro!")

if st.session_state['registro_storico']:
    st.markdown("---")
    st.header("📚 Registro Storico Mesi Salvati")
    
    mese_selezionato = st.selectbox("Seleziona il mese da visualizzare:", list(st.session_state['registro_storico'].keys()))
    
    if mese_selezionato:
        dati_mese = st.session_state['registro_storico'][mese_selezionato]
        st.write(f"**Saldo Netto Mese:** {dati_mese['saldo_netto']} minuti")
        
        tab1, tab2 = st.tabs(["Tabella Completa Mese", "Sole Timbrature Aggiunte A Mano"])
        with tab1:
            st.dataframe(dati_mese["totale_df"], use_container_width=True)
        with tab2:
            if not dati_mese["soltanmante_inserite_df"].empty:
                st.dataframe(dati_mese["soltanmante_inserite_df"], use_container_width=True)
            else:
                st.write("Nessun inserimento manuale registrato per questo mese.")

elif not api_key:
    st.warning("⚠️ Inserisci la tua API Key di Google Gemini nella barra laterale a sinistra per iniziare.")
