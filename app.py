import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
from tavily import TavilyClient
import re
import time

# --- CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="MediChat Stable", page_icon="🩺", layout="wide")

# CSS Custom
st.markdown("""
    <style>
    .stChatMessage { font-family: 'Arial', sans-serif; }
    .stButton button { width: 100%; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- VERIFICARE API KEYS ---
if "GOOGLE_API_KEY" not in st.secrets or "TAVILY_API_KEY" not in st.secrets:
    st.error("⚠️ Lipsesc cheile API! Seteaz-o în Streamlit Secrets.")
    st.stop()

# Configurare Clienti
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
tavily = TavilyClient(api_key=st.secrets["TAVILY_API_KEY"])

# --- SELECTARE MODEL (FORȚATĂ ȘI SIGURĂ) ---
# Nu mai căutăm automat modele "noi" pentru că Google ne dă modele cu limită 0.
# Folosim explicit Flash 1.5 care e gratuit și generos.

active_model_name = "Inițializare..."
try:
    # Încercăm modelul standard gratuit
    model = genai.GenerativeModel('gemini-1.5-flash')
    active_model_name = "Gemini 1.5 Flash (Standard)"
    
    # Facem un test "mut" să vedem dacă avem acces real, nu doar teoretic
    # (Nu consumăm tokens mulți, doar un 'Hi')
    response = model.generate_content("Hi")
except Exception as e:
    # Dacă 1.5 Flash dă eroare (404 sau 429), trecem pe "tancul" vechi: Gemini 1.0 Pro
    # Acesta nu moare niciodată.
    try:
        model = genai.GenerativeModel('gemini-pro')
        active_model_name = "Gemini 1.0 Pro (Legacy - Backup)"
    except Exception as e2:
        st.error(f"Eroare Totală: Niciun model nu răspunde. Verifică API Key. Detalii: {e2}")
        st.stop()

# --- FUNCȚII UTILITARE ---

def search_tavily(query):
    """Căutare Tavily cu gestionare erori"""
    try:
        response = tavily.search(
            query=query, 
            search_depth="advanced", 
            max_results=5,
            include_domains=["nih.gov", "pubmed.ncbi.nlm.nih.gov", "escardio.org", "heart.org", "who.int", "medscape.com", "mayoclinic.org"],
            topic="general"
        )
        context_text = ""
        for result in response['results']:
            context_text += f"SURSA: {result['title']}\nURL: {result['url']}\nCONȚINUT: {result['content']}\n\n"
        return context_text
    except Exception as e:
        return None

def format_links_new_tab(text):
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
    st.title("🩺 MediChat")
    # Afișăm modelul care a funcționat
    if "Backup" in active_model_name:
        st.warning(f"⚠️ {active_model_name}")
    else:
        st.success(f"✅ {active_model_name}")
    
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
        
        # 1. Căutare Tavily
        web_context = ""
        with st.spinner("Caut surse medicale (Tavily)..."):
            # Limităm lungimea query-ului pt a nu avea erori
            raw_results = search_tavily(prompt[:300])
            if raw_results:
                web_context = f"REZULTATE WEB (Surse): \n{raw_results}"
                st.caption("✅ Surse identificate.")
            else:
                st.caption("⚠️ Răspund din baza de date internă.")

        # 2. Generare Răspuns
        with st.spinner("Generez răspunsul..."):
            try:
                system_prompt = """
                ROL: Medic Consultant Senior.
                SARCINĂ: Răspunde colegial unui alt medic.
                REGULI:
                1. Bazează-te pe REZULTATELE WEB de mai jos dacă există.
                2. Citează sursele: [Nume](URL).
                3. FĂRĂ sfaturi pentru pacienți.
                """

                context_block = ""
                if use_patient_data:
                    context_block = f"""
                    PACIENT: {gender}, {age} ani, {weight}kg.
                    DOSAR: {st.session_state.patient_context}
                    """

                final_prompt = f"{system_prompt}\n{web_context}\n{context_block}\nÎNTREBARE: {prompt}"

                content_parts = [final_prompt]
                if st.session_state.images_context and use_patient_data:
                    # Unele modele vechi nu suportă imagini, tratăm cazul
                    try:
                        content_parts.append(st.session_state.images_context[0])
                    except:
                        pass # Dacă modelul nu suportă imagini, le ignorăm silențios

                response = model.generate_content(content_parts)
                
                final_html = format_links_new_tab(response.text)
                st.markdown(final_html, unsafe_allow_html=True)
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                # Tratare eroare 429 specifică
                if "429" in str(e):
                     st.error("⚠️ Prea multe cereri. Așteaptă 30 de secunde.")
                else:
                     st.error(f"Eroare: {e}")
