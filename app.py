import streamlit as st
import pandas as pd
import google.generativeai as genai
import PIL.Image
import json

st.set_page_config(page_title="Gestione Presenze & Timbrature", layout="wide")

st.title("⏱️ Gestione Presenze & Calcolo Timbrature")
st.write("Carica la foto del cartellino, verifica e completa le timbrature per ottenere il bilancio dei minuti e il riepilogo delle giustificazioni.")

st.sidebar.header("Impostazioni")
api_key = st.sidebar.text_input("Inserisci la tua Gemini API Key", type="password")

target_hours = st.sidebar.number_input("Ore turno giornaliero", value=7, min_value=0, max_value=24)
target_minutes = st.sidebar.number_input("Minuti turno giornaliero", value=36, min_value=0, max_value=59)
target_total_min = target_hours * 60 + target_minutes

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
                    # Usa il modello 3.6-flash raccomandato da Google
                    model = genai.GenerativeModel('gemini-3.6-flash')
                    prompt = """
                    Analizza questa tabella di presenze/timbrature.
                    Restituisci unicamente un array JSON di oggetti, senza formattazione Markdown extra o blocchi di codice.
                    Ogni oggetto rappresenta un giorno e deve avere queste chiavi esatte:
                    - "data": stringa (es. "01/07")
                    - "giorno": stringa (es. "Mer")
                    - "e1": stringa orario HH:MM o vuoto "" se assente
                    - "u1": stringa orario HH:MM o vuoto "" se assente
                    - "e2": stringa orario HH:MM o vuoto "" se assente
                    - "u2": stringa orario HH:MM o vuoto "" se assente

                    Se ci sono solo 2 timbrature e la seconda è dopo le 15:00, posizionala comunque su "u2" e lascia vuoti u1 ed e2.
                    """
                    response = model.generate_content([prompt, image])
                    text_resp = response.text.strip().replace("```json", "").replace("```", "")
                    data_json = json.loads(text_resp)
                    
                    df_extracted = pd.DataFrame(data_json)
                    st.session_state['df_original'] = df_extracted.copy()
                    st.session_state['df_edited'] = df_extracted.copy()
                    st.success("Estrazione completata! Puoi verificare e modificare i dati qui sotto.")
                except Exception as e:
                    st.error(f"Errore durante l'analisi: {e}")

if 'df_edited' in st.session_state:
    st.subheader("1. Griglia Timbrature (Integrazione Manuale)")
    st.info("💡 Completa le celle vuote dove mancano le timbrature. I calcoli si aggiorneranno automaticamente.")
    
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
    missing_entries = []
    
    for idx, row in edited_df.iterrows():
        e1_m = time_to_minutes(row.get('e1'))
        u1_m = time_to_minutes(row.get('u1'))
        e2_m = time_to_minutes(row.get('e2'))
        u2_m = time_to_minutes(row.get('u2'))
        
        orig_row = st.session_state['df_original'].iloc[idx] if 'df_original' in st.session_state and idx < len(st.session_state['df_original']) else {}
        added = []
        for col in ['e1', 'u1', 'e2', 'u2']:
            val = str(row.get(col, '')).strip()
            orig_val = str(orig_row.get(col, '')).strip()
            if val and val != orig_val and val not in ["nan", "None"]:
                added.append(f"{col.upper()}: {val}")
        
        if added:
            missing_entries.append({
                "Data": row.get('data'),
                "Giorno": row.get('giorno'),
                "Timbrature Inserite/Corrette": ", ".join(added)
            })
            
        total_m = 0
        if e1_m and u1_m and e2_m and u2_m:
            total_m = (u1_m - e1_m) + (u2_m - e2_m)
        elif e1_m and u2_m:
            total_m = u2_m - e1_m
        
        diff = total_m - target_total_min if total_m > 0 else 0
        
        results.append({
            "Data": row.get('data'),
            "Giorno": row.get('giorno'),
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
    
    st.dataframe(res_df, use_container_width=True)
    
    st.subheader("3. Report Timbrature Mancanti / Inserite a Mano")
    if missing_entries:
        missing_df = pd.DataFrame(missing_entries)
        st.table(missing_df)
    else:
        st.write("Nessuna timbratura inserita manualmente.")

elif not api_key:
    st.warning("⚠️ Inserisci la tua API Key di Google Gemini nella barra laterale a sinistra per iniziare.")
