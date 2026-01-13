import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
import re
from duckduckgo_search import DDGS

# --- CONFIGURARE PAGINĂ ---
st.set_page_config(page_title="MediChat Expert", page_icon="🩺", layout="wide")

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
    active_model_name = "Gemini 2.5 Flash"
except:
    model = genai.GenerativeModel('gemini-1.5-flash')
    active_model_name = "Gemini 1.5 Flash (Stabil)"

# --- FUNCȚII UTILITARE ---

def search_web(query):
    """Caută pe DuckDuckGo"""
    try:
        results_text = ""
        with DDGS() as ddgs:
            # Căutăm 5 rezultate
            results = list(ddgs.text(query, max_results=5))
            for res in results:
                # Formatăm clar pentru AI
                results_text += f"TITLU: {res['title']}\nLINK: {res['href']}\nREZUMAT: {res['body']}\n\n"
        return results_text
    except Exception as e:
        return ""

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
    st.title("🩺 MediChat Expert")
    st.caption(f"Engine: {active_model_name}")
    
    if st.button("🗑️ Resetare Caz", type="primary"):
        reset_conversation()
        st.rerun()
    
    st.markdown("---")
    
    enable_web_search = st.toggle("🌍 Adaugă Resurse Web", value=True)
    if enable_web_search:
        st.caption("Structură: Răspuns Expert AI (Bază) + Link-uri Web (Suplimentar)")
    else:
        st.caption("Strict baza de cunoștințe AI.")
    
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
        
        web_data = ""
        if enable_web_search:
            with st.spinner("Caut resurse suplimentare pe web..."):
                web_raw = search_web(prompt + " medical guidelines")
                if web_raw:
                    web_data = f"""
                    REZULTATE CĂUTARE WEB (Pentru secțiunea de resurse de la final):
                    {web_raw}
                    """

        with st.spinner("Generez analiza clinică..."):
            try:
                # --- LOGICA NOUĂ: PRIORITATE AI, APOI WEB ---
                system_prompt_core = """
                Ești un medic Consultant Senior. Discuți cu un coleg medic (Peer-to-Peer).
                
                STRUCTURA OBLIGATORIE A RĂSPUNSULUI:
                
                PARTEA 1: OPINIA CLINICĂ (BAZATĂ PE EXPERTIZA TA INTERNĂ)
                - Răspunde la întrebare folosind DOAR cunoștințele tale medicale profunde.
                - Ignoră rezultatele de pe web în această parte pentru a menține calitatea și coerența maximă.
                - Fii tehnic, precis, academic.
                - FĂRĂ disclaimers pentru pacienți (utilizatorul e medic).
                
                PARTEA 2: RESURSE WEB (Dacă există date furnizate)
                - Doar la final, adaugă o secțiune delimitată cu titlul "📚 Resurse Web Identificate".
                - Aici analizezi rezultatele căutării furnizate mai jos.
                - Listează link-urile utile găsite în format: [Titlu Sursă](URL).
                - Dacă rezultatele web sunt irelevante, ignoră această secțiune.
                """

                context_block = ""
                if use_patient_data:
                    context_block = f"""
                    DATE PACIENT: Sex: {gender}, Vârstă: {age}, Greutate: {weight}kg.
                    DOSAR MEDICAL: {st.session_state.patient_context}
                    """

                final_prompt = f"""
                {system_prompt_core}
                
                {context_block}
                
                {web_data}
                
                ÎNTREBAREA MEDICULUI: {prompt}
                """

                content_parts = [final_prompt]
                if st.session_state.images_context and use_patient_data:
                    content_parts.append(st.session_state.images_context[0]) # Adaugă imagini dacă sunt

                response = model.generate_content(content_parts)
                
                final_html = format_links_new_tab(response.text)
                st.markdown(final_html, unsafe_allow_html=True)
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                st.error(f"Eroare: {e}")
