import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
import re
from duckduckgo_search import DDGS # Biblioteca pentru căutare

# --- CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="MediChat Live", page_icon="🩺", layout="wide")

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

# --- SELECTARE MODEL ---
try:
    model = genai.GenerativeModel('gemini-2.5-flash')
    active_model_name = "Gemini 2.0 Flash"
except:
    model = genai.GenerativeModel('gemini-1.5-flash')
    active_model_name = "Gemini 1.5 Flash (Stabil)"

# --- FUNCȚII UTILITARE ---

def search_web(query):
    """Caută pe DuckDuckGo și returnează primele 5 rezultate"""
    try:
        results_text = ""
        with DDGS() as ddgs:
            # Căutăm 5 rezultate
            results = list(ddgs.text(query, max_results=5))
            for res in results:
                results_text += f"- Titlu: {res['title']}\n  Link: {res['href']}\n  Rezumat: {res['body']}\n\n"
        return results_text
    except Exception as e:
        return f"Eroare la căutare: {e}"

def format_links_new_tab(text):
    """Transformă link-urile Markdown în HTML cu target='_blank'"""
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    def replace_link(match):
        link_text = match.group(1)
        link_url = match.group(2)
        return f'<a href="{link_url}" target="_blank" style="color: #0068c9; text-decoration: none; font-weight: bold;">{link_text} 🔗</a>'
    return re.sub(pattern, replace_link, text)

def reset_conversation():
    st.session_state.messages = []
    st.session_state.patient_context = ""
    st.session_state.images_context = []

def generate_download_text():
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

# --- SIDEBAR ---
with st.sidebar:
    st.title("🩺 MediChat Live")
    st.caption(f"Sistem: {active_model_name}")
    
    if st.button("🗑️ Pacient Nou / Resetare", type="primary"):
        reset_conversation()
        st.rerun()
    
    st.markdown("---")
    
    # OPȚIUNEA DE CĂUTARE WEB
    enable_web_search = st.toggle("🌍 Activare Căutare Web (Live)", value=True)
    if enable_web_search:
        st.caption("AI-ul va căuta pe internet pentru fiecare întrebare.")
    else:
        st.caption("Doar cunoștințe interne (mai rapid).")

    st.markdown("---")
    
    # DATE PACIENT
    use_patient_data = st.toggle("Mod: Caz Clinic Pacient", value=False)
    
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
        st.download_button("💾 Descarcă TXT", generate_download_text(), "consult.txt")

# --- CHAT ---
st.subheader("Discuție Medicală")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            st.markdown(format_links_new_tab(message["content"]), unsafe_allow_html=True)
        else:
            st.markdown(message["content"])

if prompt := st.chat_input("Întrebare..."):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # Logica de Căutare + Generare
        status_text = "Analizez..."
        web_context = ""
        
        # 1. Dacă e activată căutarea, căutăm pe net
        if enable_web_search:
            status_text = "Caut pe internet în timp real..."
            with st.spinner(status_text):
                search_results = search_web(prompt + " medical guidelines")
                web_context = f"\n\nINFORMAȚII GĂSITE PE WEB (REAL-TIME):\n{search_results}\nFolosește link-urile de mai sus pentru referințe."

        # 2. Generăm răspunsul
        with st.spinner("Generez răspunsul..."):
            try:
                sources_request = """
                CERINȚE:
                1. Dacă ai primit informații de pe web, folosește-le.
                2. Include link-uri: [Nume](URL).
                """

                if use_patient_data:
                    system_prompt = f"""
                    Ești un asistent medical expert.
                    DATE PACIENT: Sex: {gender}, Vârstă: {age}, Greutate: {weight}kg.
                    DOSAR: {st.session_state.patient_context}
                    {web_context}
                    {sources_request}
                    Răspunde specific.
                    """
                    content_parts = [system_prompt, prompt]
                    if st.session_state.images_context:
                        content_parts.extend(st.session_state.images_context)
                else:
                    system_prompt = f"""
                    Ești un asistent medical expert.
                    {web_context}
                    {sources_request}
                    """
                    content_parts = [system_prompt, prompt]

                response = model.generate_content(content_parts)
                final_html = format_links_new_tab(response.text)
                st.markdown(final_html, unsafe_allow_html=True)
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                st.error(f"Eroare: {e}")
