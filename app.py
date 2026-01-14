import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
from tavily import TavilyClient
import re

# --- CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="MediChat Auto", page_icon="🩺", layout="wide")

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

# --- FUNCȚIE INTELIGENTĂ DE SELECTARE MODEL ---
def get_best_available_model():
    """
    Încearcă o listă de modele cunoscute până găsește unul care merge.
    Rezolvă eroarea 404 Not Found.
    """
    # Lista de priorități: De la cel mai nou/rapid la cel mai vechi/sigur
    candidate_models = [
        'gemini-1.5-flash',
        'gemini-1.5-flash-latest',
        'gemini-1.5-flash-001',
        'gemini-1.5-pro',
        'gemini-1.5-pro-latest',
        'gemini-1.0-pro',
        'gemini-pro' # Cel mai vechi, dar merge mereu
    ]
    
    for model_name in candidate_models:
        try:
            # Încercăm să inițializăm modelul
            model = genai.GenerativeModel(model_name)
            return model, model_name
        except:
            continue
            
    # Dacă nimic nu merge, returnăm default (va crăpa mai jos, dar măcar încercăm)
    return genai.GenerativeModel('gemini-pro'), "Gemini Pro (Legacy)"

# Inițializăm modelul folosind funcția de mai sus
model, active_model_name = get_best_available_model()

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
    st.title("🩺 MediChat Pro")
    st.success(f"✅ Conectat: {active_model_name}")
    st.caption("Auto-Detect Mode Active")
    
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
            raw_results = search_tavily(prompt[:300])
            if raw_results:
                web_context = f"REZULTATE WEB EXTREM DE RELEVANTE:\n{raw_results}"
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
                    content_parts.append(st.session_state.images_context[0])

                response = model.generate_content(content_parts)
                
                final_html = format_links_new_tab(response.text)
                st.markdown(final_html, unsafe_allow_html=True)
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                # Dacă primim 404 sau 429 aici, înseamnă că modelul ales totuși a făcut figuri
                # Încercăm un ultim resort (Gemini Pro vechi)
                if "404" in str(e) or "429" in str(e):
                    try:
                        fallback_model = genai.GenerativeModel('gemini-pro')
                        response = fallback_model.generate_content(content_parts)
                        st.markdown(format_links_new_tab(response.text), unsafe_allow_html=True)
                        st.caption("ℹ️ Răspuns generat cu modelul de rezervă (Legacy).")
                        st.session_state.messages.append({"role": "assistant", "content": response.text})
                    except:
                         st.error(f"Eroare critică API: {e}. Verifică Quota.")
                else:
                    st.error(f"Eroare: {e}")
