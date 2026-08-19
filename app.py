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
                    text_resp = response.text.strip().replace("```json", "").replace("
