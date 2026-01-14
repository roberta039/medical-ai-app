import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
from tavily import TavilyClient
import re
import time

# --- CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="MediChat Auto-Fix", page_icon="🩺", layout="wide")

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

# --- SELECTARE MODEL DINAMICĂ (CRITIC) ---
@st.cache_resource
def find_and_load_model():
    """
    Scanează contul pentru ORICE model disponibil și îl returnează.
    """
    log_text = ""
    try:
        # 1. Cerem lista de la Google
        all_models = list(genai.list_models())
        available_names = []
        
        # 2. Filtrăm doar modelele care pot genera text
        for m in all_models:
            if 'generateContent' in m.supported_generation_methods:
                available_names.append(m.name)
        
        log_text = f"Modele găsite pe cont: {available_names}"
        
        if not available_names:
            return None, "Niciun model găsit pe acest API Key.", log_text

        # 3. Alegem cel mai bun (Flash > Pro > Orice altceva)
        chosen_model_name = available_names[0] # Default primul
        
        # Încercăm să găsim Flash (e cel mai rapid/ieftin)
        for name in available_names:
            if "flash" in name and "1.5" in name:
                chosen_model_name = name
                break
        
        # Dacă nu Flash, încercăm Pro 1.5
        if "flash" not in chosen_model_name:
             for name in available_names:
                if "pro" in name and "1.5" in name:
                    chosen_model_name = name
                    break
        
        # 4. Inițializăm
        model = genai.GenerativeModel(chosen_model_name)
        return model, chosen_model_name, log_text

    except Exception as e:
        return None, str(e), log_text

# Încărcare model la start
model, model_name, debug_log = find_and_load_model()

# Dacă totul a eșuat
if not model:
    st.error("❌ EROARE CRITICĂ: Nu am putut conecta niciun model AI.")
    st.code(debug_log)
    st.info("Soluție: Mergi în Google AI Studio, creează un proiect nou și o cheie API nouă.")
    st.stop()

# --- FUNCȚII UTILITARE ---

def search_tavily(query):
    try:
        response = tavily.search(
            query=query, 
            search_depth="advanced", 
            max_results=5,
            include_domains=["nih.gov", "pubmed.ncbi.nlm.nih.gov", "escardio.org", "heart.org", "who.int", "medscape.com"],
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
    st.success(f"✅ Conectat: {model_name.replace('models/', '')}")
    
    # Debug expander (pentru a vedea ce se întâmplă)
    with st.expander("🛠️ Detalii Tehnice"):
        st.caption("Modele detectate pe cont:")
        st.code(debug_log)

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
        
        web_context = ""
        with st.spinner("Caut surse medicale (Tavily)..."):
            raw_results = search_tavily(prompt[:300])
            if raw_results:
                web_context = f"REZULTATE WEB (Surse):\n{raw_results}"
                st.caption("✅ Surse identificate.")
            else:
                st.caption("⚠️ Răspund din baza de date internă.")

        with st.spinner("Generez răspunsul..."):
            try:
                system_prompt = """
                ROL: Medic Consultant Senior.
                SARCINĂ: Răspunde colegial unui alt medic.
                REGULI:
                1. Bazează-te PRIORITAR pe REZULTATELE WEB de mai jos.
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
                     # Încercăm să adăugăm imaginea, dacă modelul suportă
                    try:
                        content_parts.append(st.session_state.images_context[0])
                    except:
                        pass

                response = model.generate_content(content_parts)
                
                final_html = format_links_new_tab(response.text)
                st.markdown(final_html, unsafe_allow_html=True)
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                st.error(f"Eroare: {e}")
