import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
from google.api_core import exceptions

# --- CONFIGURARE ---
st.set_page_config(page_title="MediChat Pro + Surse", page_icon="🩺", layout="wide")

# Configurare API Key
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("⚠️ Cheia API lipsește! Seteaz-o în Streamlit Secrets.")

# --- DEFINIREA UNELTEI DE CĂUTARE ---
# Aceasta este sintaxa corectă pentru versiunile noi
google_search_tool = [
    {"google_search": {}}
]

# Selectare Model
try:
    # Încercăm 2.0 cu Search
    model = genai.GenerativeModel(
        'gemini-2.0-flash-exp',
        tools=google_search_tool
    )
    active_model = "Gemini 2.0 (Google Search)"
except:
    try:
        # Încercăm 1.5 cu Search
        model = genai.GenerativeModel(
            'gemini-1.5-flash',
            tools=google_search_tool
        )
        active_model = "Gemini 1.5 (Google Search)"
    except:
        # Fallback fără search (dacă totuși dă eroare)
        model = genai.GenerativeModel('gemini-1.5-flash')
        active_model = "Gemini 1.5 (Fără Search - Mod Siguranță)"

# --- INITIALIZARE STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "patient_context" not in st.session_state:
    st.session_state.patient_context = ""
if "images_context" not in st.session_state:
    st.session_state.images_context = []

# --- SIDEBAR ---
with st.sidebar:
    st.title("🩺 MediChat")
    st.caption(f"Status: {active_model}")
    
    use_patient_data = st.toggle("Activează Context Pacient", value=False)
    
    if use_patient_data:
        st.info("Mod: Caz Clinic")
        gender = st.selectbox("Sex", ["Masculin", "Feminin"])
        age = st.number_input("Vârstă", value=30)
        weight = st.number_input("Greutate (kg)", value=70.0)
        
        uploaded_files = st.file_uploader("Dosar Medical", type=['pdf', 'png', 'jpg'], accept_multiple_files=True)
        
        if st.button("Procesează"):
            if uploaded_files:
                with st.spinner("Analiză..."):
                    raw_text = ""
                    images = []
                    for file in uploaded_files:
                        if file.type == "application/pdf":
                            reader = PdfReader(file)
                            for page in reader.pages:
                                raw_text += page.extract_text() + "\n"
                        else:
                            images.append(Image.open(file))
                    
                    st.session_state.patient_context = raw_text
                    st.session_state.images_context = images
                    st.success("Date încărcate.")
    else:
        st.info("Mod: Întrebări Generale")
        st.caption("AI-ul va căuta surse pe internet pentru răspunsuri.")
        st.session_state.patient_context = ""
        st.session_state.images_context = []

# --- CHAT ---
st.subheader("Discuție Medicală & Surse")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Întrebare medicală..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Caut informații verificate..."):
            try:
                # Prompt specific pentru link-uri
                sources_prompt = "Te rog să cauți pe Google și să oferi LINK-uri reale către sursele medicale (Ghiduri, Studii)."
                
                if use_patient_data:
                    system_prompt = f"""
                    Ești un asistent medical expert. {sources_prompt}
                    DATE PACIENT: Sex: {gender}, Vârstă: {age}, Greutate: {weight}kg.
                    CONTEXT DOSAR: {st.session_state.patient_context}
                    Răspunde specific pentru acest pacient.
                    """
                    content_parts = [system_prompt, prompt]
                    if st.session_state.images_context:
                        content_parts.extend(st.session_state.images_context)
                else:
                    system_prompt = f"Ești un asistent medical expert. {sources_prompt} Răspunde la întrebări generale."
                    content_parts = [system_prompt, prompt]

                response = model.generate_content(content_parts)
                st.markdown(response.text)
                
                # Afișare link-uri surse (dacă există în metadata)
                try:
                    if hasattr(response.candidates[0], 'grounding_metadata'):
                        gm = response.candidates[0].grounding_metadata
                        if hasattr(gm, 'search_entry_point') and gm.search_entry_point:
                             st.markdown(f"🔍 *Sursă verificată:* {gm.search_entry_point.rendered_content}")
                except:
                    pass

                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                st.error(f"Eroare: {e}. Dacă eroarea persistă, debifează modul 'Surse' sau reîmprospătează pagina.")
