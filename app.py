import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
import re

# --- CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="MediChat Stabil", page_icon="🩺", layout="wide")

# CSS Custom
st.markdown("""
    <style>
    .stChatMessage { font-family: 'Arial', sans-serif; }
    .stButton button { width: 100%; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# Configurare API Key
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("⚠️ Cheia API lipsește! Seteaz-o în Streamlit Secrets.")

# --- SELECTARE MODEL (FĂRĂ TOOLS) ---
# Aceasta este configurația cea mai sigură care nu dă 404.
try:
    # Încercăm modelul experimental (mai deștept)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    active_model_name = "Gemini 2.0 Flash (Exp)"
except:
    # Fallback la modelul stabil
    model = genai.GenerativeModel('gemini-1.5-flash')
    active_model_name = "Gemini 1.5 Flash (Stabil)"

# --- FUNCȚII UTILITARE ---

def format_links_new_tab(text):
    """
    Transformă link-urile Markdown [Text](URL) în HTML care se deschide în tab nou.
    """
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    def replace_link(match):
        link_text = match.group(1)
        link_url = match.group(2)
        # Verificăm sumar dacă pare un URL valid
        if "http" not in link_url:
            return link_text 
        return f'<a href="{link_url}" target="_blank" style="color: #0068c9; text-decoration: none; font-weight: bold;">{link_text} 🔗</a>'
    return re.sub(pattern, replace_link, text)

def reset_conversation():
    st.session_state.messages = []
    st.session_state.patient_context = ""
    st.session_state.images_context = []

def generate_download_text():
    text = "--- RAPORT CLINIC ---\n\n"
    for msg in st.session_state.messages:
        role = "MEDIC" if msg["role"] == "user" else "AI"
        text += f"{role}: {msg['content']}\n\n"
    return text

# --- INITIALIZARE STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "patient_context" not in st.session_state:
    st.session_state.patient_context = ""
if "images_context" not in st.session_state:
    st.session_state.images_context = []

# --- SIDEBAR ---
with st.sidebar:
    st.title("🩺 MediChat Pro")
    st.caption(f"Sistem: {active_model_name}")
    
    if st.button("🗑️ Resetare Caz", type="primary"):
        reset_conversation()
        st.rerun()
    
    st.markdown("---")
    
    use_patient_data = st.toggle("Mod: Caz Clinic", value=False)
    
    if use_patient_data:
        st.info("📊 Date Pacient")
        col1, col2 = st.columns(2)
        with col1:
            gender = st.selectbox("Sex", ["M", "F"], label_visibility="collapsed")
        with col2:
            age = st.number_input("Ani", value=30, label_visibility="collapsed")
        weight = st.number_input("Greutate (kg)", value=70.0)
        uploaded_files = st.file_uploader("Dosar", type=['pdf', 'png', 'jpg'], accept_multiple_files=True)
        
        if st.button("Procesează Dosarul"):
            if uploaded_files:
                with st.spinner("Se citește dosarul..."):
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
                    st.success("Date încărcate!")
    else:
        st.session_state.patient_context = ""
        st.session_state.images_context = []

    if st.session_state.messages:
        st.download_button("💾 Export Discuție", generate_download_text(), "consult.txt")

# --- CHAT ---
st.subheader("Discuție Clinică")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            st.markdown(format_links_new_tab(message["content"]), unsafe_allow_html=True)
        else:
            st.markdown(message["content"])

if prompt := st.chat_input("Introdu datele clinice sau întrebarea..."):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analiză clinică..."):
            try:
                # --- PROMPT STRICT PENTRU LINK-URI DIN MEMORIE ---
                system_prompt = """
                ROL: Ești un medic Consultant Senior (Peer-to-Peer).
                
                REGULI:
                1. Răspunde colegial, tehnic și la obiect.
                2. FĂRĂ sfaturi pentru pacienți. Utilizatorul este medic.
                
                CERINȚĂ SPECIALĂ PENTRU SURSE:
                - Deoarece ești expert, cunoști marile ghiduri (ESC, AHA, ADA, NICE, MS.ro).
                - Când faci o recomandare, citează ghidul și oferă link-ul oficial dacă îl știi.
                - FORMAT OBLIGATORIU LINK: [Nume Sursă](URL_COMPLET).
                - Exemplu: [Ghid ESC 2023](https://www.escardio.org/...)
                """

                context_block = ""
                if use_patient_data:
                    context_block = f"""
                    DATE PACIENT: Sex: {gender}, Vârstă: {age}, Greutate: {weight}kg.
                    DOSAR: {st.session_state.patient_context}
                    """

                final_prompt = f"{system_prompt}\n{context_block}\nÎNTREBARE: {prompt}"

                content_parts = [final_prompt]
                if st.session_state.images_context and use_patient_data:
                    content_parts.append(st.session_state.images_context[0])

                # Generare SIMPLĂ (Fără tools, deci fără erori 404)
                response = model.generate_content(content_parts)
                
                final_html = format_links_new_tab(response.text)
                st.markdown(final_html, unsafe_allow_html=True)
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                # Acum eroarea ar trebui să fie imposibilă, dar o prindem just in case
                st.error(f"Eroare neașteptată: {e}. Încearcă să reîncarci pagina.")
