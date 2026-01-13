import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image

# --- CONFIGURARE ---
st.set_page_config(page_title="MediChat Stabil", page_icon="🩺", layout="wide")

# Configurare API Key
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("⚠️ Cheia API lipsește! Seteaz-o în Streamlit Secrets.")

# --- INITIALIZARE MODEL (FĂRĂ TOOLS CARE DAU EROARE) ---
# Folosim modelul standard, fără configurații exotice care pot da 404
try:
    # Încercăm întâi 2.5 (dacă e disponibil)
    model = genai.GenerativeModel('gemini-2.5-flash')
    active_model_name = "Gemini 2.5 Flash"
except:
    # Dacă nu, fallback sigur la 1.5
    model = genai.GenerativeModel('gemini-1.5-flash')
    active_model_name = "Gemini 1.5 Flash (Stabil)"

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
    st.success(f"Sistem Online: {active_model_name}")
    st.markdown("---")
    
    use_patient_data = st.toggle("Mod: Caz Clinic Pacient", value=False)
    
    if use_patient_data:
        st.info("Completează datele")
        gender = st.selectbox("Sex", ["Masculin", "Feminin"])
        age = st.number_input("Vârstă", value=30)
        weight = st.number_input("Greutate (kg)", value=70.0)
        
        uploaded_files = st.file_uploader("Dosar (PDF/Foto)", type=['pdf', 'png', 'jpg'], accept_multiple_files=True)
        
        if st.button("Procesează Dosarul"):
            if uploaded_files:
                with st.spinner("Se citește..."):
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
                    st.success("Date citite!")
    else:
        st.info("Mod: General / Teoretic")
        st.caption("Întreabă despre ghiduri, tratamente, protocoale.")
        st.session_state.patient_context = ""
        st.session_state.images_context = []

# --- CHAT ---
st.subheader("Asistent Medical AI")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Scrie întrebarea..."):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analizez literatura medicală..."):
            try:
                # INSTRUCȚIUNE PENTRU LINK-URI (Prompt Engineering)
                # Îi cerem explicit să pună link-uri, fără să folosim tool-ul care dă eroare.
                sources_request = """
                CERINȚĂ SUPLIMENTARĂ IMPORTANTĂ:
                Te rog să incluzi, unde este posibil, referințe către ghiduri (ESC, AHA, NICE) sau studii.
                Dacă menționezi un ghid, încearcă să oferi URL-ul oficial sau numele exact al documentului.
                """

                if use_patient_data:
                    system_prompt = f"""
                    Ești un consultant medical expert.
                    DATE PACIENT: Sex: {gender}, Vârstă: {age}, Greutate: {weight}kg.
                    CONTEXT DOSAR: {st.session_state.patient_context}
                    
                    {sources_request}
                    
                    Răspunde specific pentru acest caz.
                    """
                    content_parts = [system_prompt, prompt]
                    if st.session_state.images_context:
                        content_parts.extend(st.session_state.images_context)
                else:
                    system_prompt = f"""
                    Ești un consultant medical expert.
                    Răspunde la întrebări generale bazate pe ghiduri clinice.
                    
                    {sources_request}
                    """
                    content_parts = [system_prompt, prompt]

                # Generare simplă (cea mai sigură metodă)
                response = model.generate_content(content_parts)
                
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                # Dacă totuși apare o eroare ciudată, o afișăm prietenos
                st.error(f"A apărut o eroare de conexiune cu Google AI. Reîncearcă în câteva secunde. Detalii: {e}")
