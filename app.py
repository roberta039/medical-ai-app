import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
import re

# --- CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="MediChat Pro", page_icon="🩺", layout="wide")

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

# --- INITIALIZARE MODEL INTELIGENTĂ ---
# Definim unealta de căutare Google Nativă
google_search_tool = [{"google_search": {}}]

active_model_name = ""
has_search_capability = False

try:
    # 1. Încercăm varianta IDEALĂ: Gemini 2.5 + Google Search
    model = genai.GenerativeModel('gemini-2.5-flash', tools=google_search_tool)
    active_model_name = "Gemini 2.5 (Google Search Activat)"
    has_search_capability = True
except Exception as e:
    try:
        # 2. Dacă 2.0 nu merge, încercăm 1.5 + Google Search
        # (Unele conturi au acces, altele nu - testăm)
        model = genai.GenerativeModel('gemini-1.5-flash', tools=google_search_tool)
        active_model_name = "Gemini 1.5 (Google Search Activat)"
        has_search_capability = True
    except:
        # 3. FALLBACK SIGUR: Gemini 1.5 (Memorie Internă)
        # Aici ajungem dacă Google Search e blocat pe cont. Măcar AI-ul merge perfect.
        model = genai.GenerativeModel('gemini-1.5-flash')
        active_model_name = "Gemini 1.5 (Expertiză Internă)"
        has_search_capability = False

# --- FUNCȚII UTILITARE ---

def format_links_new_tab(text):
    """Link-uri Markdown -> HTML New Tab"""
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
    
    # Indicator Status
    if has_search_capability:
        st.success(f"✅ {active_model_name}")
    else:
        st.info(f"🧠 {active_model_name}")
        
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
            # Afișăm și sursele Google dacă există (Grounding)
            st.markdown(format_links_new_tab(message["content"]), unsafe_allow_html=True)
        else:
            st.markdown(message["content"])

if prompt := st.chat_input("Introdu datele clinice sau întrebarea..."):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analiză în curs..."):
            try:
                # --- PROMPT DESIGN ---
                # Dacă avem search activat, îi spunem să îl folosească
                search_instruction = ""
                if has_search_capability:
                    search_instruction = """
                    FOLOSEȘTE GOOGLE SEARCH: Verifică ghidurile actuale.
                    Dacă găsești surse relevante, include link-urile la final.
                    """

                system_prompt = f"""
                Ești un medic Consultant Senior (Peer-to-Peer).
                
                REGULI:
                1. Răspunde colegial, tehnic și la obiect.
                2. FĂRĂ sfaturi pentru pacienți ("consultați medicul"). Utilizatorul este medic.
                3. Bazează-te pe expertiza ta internă + Search (dacă e disponibil).
                {search_instruction}
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

                # Generare (Gestionăm eroarea de 404 aici, local)
                try:
                    response = model.generate_content(content_parts)
                    
                    # Afișare răspuns
                    final_html = format_links_new_tab(response.text)
                    st.markdown(final_html, unsafe_allow_html=True)
                    
                    # Afișare surse Google Grounding (Metadate oficiale)
                    if hasattr(response.candidates[0], 'grounding_metadata'):
                        gm = response.candidates[0].grounding_metadata
                        if hasattr(gm, 'search_entry_point') and gm.search_entry_point:
                             st.caption(f"🔍 Sursă Verificată Google: {gm.search_entry_point.rendered_content}")

                    st.session_state.messages.append({"role": "assistant", "content": response.text})

                except Exception as e_gen:
                    # Dacă modelul cu Search dă fail (404 sau altceva) în timpul generării,
                    # facem fallback instant la modelul simplu (1.5) fără să știe utilizatorul.
                    fallback_model = genai.GenerativeModel('gemini-1.5-flash')
                    response = fallback_model.generate_content(content_parts)
                    
                    final_html = format_links_new_tab(response.text)
                    st.markdown(final_html, unsafe_allow_html=True)
                    st.caption("ℹ️ Răspuns generat din expertiză internă (Search indisponibil momentan).")
                    
                    st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                st.error(f"Eroare sistem: {e}")
