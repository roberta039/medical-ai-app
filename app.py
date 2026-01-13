import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
import re

# --- CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="MediChat Pro", page_icon="🩺", layout="wide")

# --- CSS PENTRU ASPECT PROFESIONAL ---
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

# --- SELECTARE MODEL ---
try:
    model = genai.GenerativeModel('gemini-2.5-flash')
    active_model_name = "Gemini 2.5 Flash"
except:
    model = genai.GenerativeModel('gemini-1.5-flash')
    active_model_name = "Gemini 1.5 Flash (Stabil)"

# --- FUNCȚII UTILITARE ---

def format_links_new_tab(text):
    """Transformă link-urile Markdown în HTML cu target='_blank'"""
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    def replace_link(match):
        link_text = match.group(1)
        link_url = match.group(2)
        return f'<a href="{link_url}" target="_blank" style="color: #0068c9; text-decoration: none; font-weight: bold;">{link_text} 🔗</a>'
    return re.sub(pattern, replace_link, text)

def reset_conversation():
    """Șterge istoricul pentru a începe un pacient nou"""
    st.session_state.messages = []
    st.session_state.patient_context = ""
    st.session_state.images_context = []
    # Nu folosim st.rerun() direct aici pentru a evita bucle, Streamlit se va actualiza oricum

def generate_download_text():
    """Creează un text simplu din conversație pentru descărcare"""
    text = "--- RAPORT MEDICHAT ---\n\n"
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

# --- SIDEBAR (PANOU CONTROL) ---
with st.sidebar:
    st.title("🩺 MediChat")
    st.caption(f"Sistem: {active_model_name}")
    st.markdown("---")
    
    # 1. ZONA DE RESET (NOU)
    if st.button("🗑️ Pacient Nou / Resetare", type="primary"):
        reset_conversation()
        st.rerun()

    st.markdown("---")
    
    # 2. ZONA DE DATE PACIENT
    use_patient_data = st.toggle("Mod: Caz Clinic Pacient", value=False)
    
    if use_patient_data:
        st.info("📊 Date Pacient")
        col1, col2 = st.columns(2)
        with col1:
            gender = st.selectbox("Sex", ["M", "F"], label_visibility="collapsed")
        with col2:
            age = st.number_input("Ani", value=30, label_visibility="collapsed")
        
        weight = st.number_input("Greutate (kg)", value=70.0)
        
        uploaded_files = st.file_uploader("Dosar (PDF/Foto)", type=['pdf', 'png', 'jpg'], accept_multiple_files=True)
        
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
                    st.success("✅ Date încărcate!")
    else:
        st.info("Mod: General / Teoretic")
        st.session_state.patient_context = ""
        st.session_state.images_context = []

    st.markdown("---")
    
    # 3. ZONA DE DESCĂRCARE (NOU)
    if st.session_state.messages:
        st.download_button(
            label="💾 Descarcă Discuția (TXT)",
            data=generate_download_text(),
            file_name="consult_medical.txt",
            mime="text/plain"
        )

# --- CHAT AREA ---
st.subheader("Discuție Medicală")

# Afișare mesaje
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            formatted_content = format_links_new_tab(message["content"])
            st.markdown(formatted_content, unsafe_allow_html=True)
        else:
            st.markdown(message["content"])

# Input Utilizator
if prompt := st.chat_input("Scrie întrebarea medicală..."):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Gândesc..."):
            try:
                # PROMPT PRINCIPAL
                sources_request = """
                CERINȚE FORMAT:
                1. Include link-uri către ghiduri (ESC, AHA, MS.ro) unde e cazul.
                2. FORMAT LINK OBLIGATORIU: [Nume Sursă](URL_COMPLET).
                3. Exemplu: [Ghid ESC](https://www.escardio.org).
                """

                if use_patient_data:
                    system_prompt = f"""
                    Ești un asistent medical expert.
                    DATE PACIENT: Sex: {gender}, Vârstă: {age}, Greutate: {weight}kg.
                    DOSAR: {st.session_state.patient_context}
                    
                    {sources_request}
                    
                    Răspunde specific pentru acest pacient.
                    """
                    content_parts = [system_prompt, prompt]
                    if st.session_state.images_context:
                        content_parts.extend(st.session_state.images_context)
                else:
                    system_prompt = f"""
                    Ești un asistent medical expert. Răspunde la întrebări generale.
                    {sources_request}
                    """
                    content_parts = [system_prompt, prompt]

                # Generare
                response = model.generate_content(content_parts)
                
                # Formatare și Afișare
                final_html_text = format_links_new_tab(response.text)
                st.markdown(final_html_text, unsafe_allow_html=True)
                
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                st.error(f"Eroare: {e}")
