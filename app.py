import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
from tavily import TavilyClient
import re
import datetime

# --- 1. CONFIGURARE PAGINĂ & STIL ---
st.set_page_config(page_title="MediChat AI Pro", page_icon="🩺", layout="wide")

# CSS pentru stilizare
st.markdown("""
    <style>
    .stChatMessage { font-family: 'Arial', sans-serif; }
    .stButton button { width: 100%; border-radius: 8px; }
    div[data-baseweb="input"] { background-color: #f0f2f6; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DISCLAIMER OBLIGATORIU ---
st.warning("⚠️ **AVERTISMENT:** Asistent AI experimental. Verificați întotdeauna ghidurile oficiale. Nu introduceți date personale (GDPR).")

# --- 3. VERIFICARE API KEYS ---
if "GOOGLE_API_KEY" not in st.secrets or "TAVILY_API_KEY" not in st.secrets:
    st.error("⚠️ Lipsesc cheile API! Setează `GOOGLE_API_KEY` și `TAVILY_API_KEY` în Streamlit Secrets.")
    st.stop()

# Configurare Clienti
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
tavily = TavilyClient(api_key=st.secrets["TAVILY_API_KEY"])

# --- 4. FUNCȚII UTILITARE & MODEL ---

@st.cache_resource
def load_best_model():
    """Găsește cel mai bun model Gemini disponibil pe cont."""
    try:
        all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        chosen_model = next((m for m in all_models if "flash" in m and "1.5" in m), None)
        if not chosen_model:
            chosen_model = next((m for m in all_models if "pro" in m and "1.5" in m), all_models[0])
        return genai.GenerativeModel(chosen_model), chosen_model
    except Exception as e:
        return None, str(e)

model, model_name = load_best_model()

if not model:
    st.error("❌ Nu am putut încărca modelul AI. Verifică API Key-ul.")
    st.stop()

def search_tavily(query):
    """Caută pe site-uri medicale, forțând rezultate recente."""
    try:
        # MODIFICARE MAJORĂ: Forțăm căutarea să fie recentă
        current_year = datetime.datetime.now().year
        optimized_query = f"{query} latest clinical guidelines medical research updates {current_year} {current_year-1}"
        
        response = tavily.search(
            query=optimized_query, 
            search_depth="advanced", 
            max_results=6, # Căutăm mai multe rezultate
            include_domains=["nih.gov", "pubmed.ncbi.nlm.nih.gov", "escardio.org", "heart.org", "who.int", "medscape.com", "mayoclinic.org", "nejm.org", "thelancet.com"],
            topic="general"
        )
        context_text = ""
        for result in response['results']:
            context_text += f"- SURSA: {result['title']}\n  URL: {result['url']}\n  INFO: {result['content']}\n\n"
        return context_text
    except Exception as e:
        return ""

def format_links(text):
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    return re.sub(pattern, r'<a href="\2" target="_blank" style="color: #0068c9; font-weight: bold;">\1 🔗</a>', text)

def transcribe_audio(audio_bytes):
    try:
        prompt_transcribe = "Transcrede acest fișier audio exact în limba română. Este o întrebare medicală."
        response = model.generate_content([prompt_transcribe, {"mime_type": "audio/wav", "data": audio_bytes}])
        return response.text
    except Exception as e:
        return None

def generate_report_text(gender, age, weight, patient_context, messages):
    txt = f"=== RAPORT MEDICAL AI ===\nData: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
    txt += "--- DATE PACIENT ---\n"
    txt += f"Gen: {gender}\nVarsta: {age} ani\nGreutate: {weight} kg\n"
    if patient_context:
        txt += f"Context Dosar: {len(patient_context)} caractere extrase.\n"
    else:
        txt += "Context Dosar: Fără documente încărcate.\n"
    
    txt += "\n--- ISTORIC CONSULTAȚIE ---\n"
    for msg in messages:
        role = "MEDIC" if msg["role"] == "user" else "AI"
        content = msg["content"].replace("**", "").replace("__", "")
        txt += f"\n[{role}]: {content}\n"
        txt += "-" * 40 + "\n"
    return txt

# --- 5. GESTIONARE STARE ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "patient_context" not in st.session_state:
    st.session_state.patient_context = ""
if "images_context" not in st.session_state:
    st.session_state.images_context = []

# --- 6. SIDEBAR (CONTROALE) ---
with st.sidebar:
    st.title("🩺 Control Panel")
    
    col_set_1, col_set_2 = st.columns(2)
    with col_set_1:
        use_web_search = st.toggle("🌐 Internet", value=True, help="Caută cele mai recente ghiduri (2024-2025).")
    with col_set_2:
        use_patient_mode = st.toggle("📂 Dosar", value=False)

    st.divider()
    
    gender_exp, age_exp, weight_exp = "N/A", "N/A", "N/A"

    if use_patient_mode:
        st.subheader("📝 Date Pacient")
        st.info("Introduceți detaliile pentru context.")
        
        gender = st.selectbox("Gen / Sex", ["Masculin", "Feminin"], index=0)
        age = st.number_input("Vârstă (Ani)", min_value=0, max_value=120, value=45, step=1)
        weight = st.number_input("Greutate (Kg)", min_value=0.0, max_value=300.0, value=75.0, step=0.1, format="%.1f")
        
        gender_exp, age_exp, weight_exp = gender, age, weight

        st.markdown("**Atașează Documente:**")
        uploaded_files = st.file_uploader("PDF Analize / Poze EKG...", type=['pdf', 'png', 'jpg', 'jpeg'], accept_multiple_files=True)
        
        if uploaded_files:
            raw_text = ""
            images = []
            for file in uploaded_files:
                if file.type == "application/pdf":
                    try:
                        reader = PdfReader(file)
                        for page in reader.pages:
                            text_page = page.extract_text()
                            if text_page: raw_text += text_page + "\n"
                    except:
                        st.error(f"Eroare fișier: {file.name}")
                else:
                    images.append(Image.open(file))
            
            st.session_state.patient_context = raw_text
            st.session_state.images_context = images
            if raw_text or images:
                st.caption(f"✅ Sistem: {len(images)} imagini, text extras.")
    else:
        st.session_state.patient_context = ""
        st.session_state.images_context = []

    st.divider()
    
    st.subheader("💾 Export")
    if st.session_state.messages:
        report_data = generate_report_text(gender_exp, age_exp, weight_exp, st.session_state.patient_context, st.session_state.messages)
        st.download_button(
            label="📄 Descarcă Raport (.txt)",
            data=report_data,
            file_name=f"Raport_Medical_{datetime.datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain"
        )
    
    if st.button("🗑️ Conversație Nouă", type="primary"):
        st.session_state.messages = []
        st.rerun()

# --- 7. INTERFAȚA DE CHAT ---
st.subheader("💬 Asistent Medical")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            st.markdown(format_links(msg["content"]), unsafe_allow_html=True)
        else:
            st.markdown(msg["content"])

# --- 8. INPUT (VOCE & TEXT) ---
audio_val = st.audio_input("🎤 Dictare (beta)")
voice_text = ""

if audio_val:
    with st.spinner("🎧 Transcriu..."):
        audio_bytes = audio_val.read()
        transcription = transcribe_audio(audio_bytes)
        if transcription: voice_text = transcription

user_input = st.chat_input("Scrie întrebarea aici...")

final_prompt = None
if user_input:
    final_prompt = user_input
elif voice_text and audio_val: 
    final_prompt = voice_text

# --- 9. PROCESARE ---
if final_prompt:
    
    st.session_state.messages.append({"role": "user", "content": final_prompt})
    with st.chat_message("user"):
        st.markdown(final_prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        
        # 1. SEARCH UPDATE: Tavily va căuta explicit 2024-2025
        web_context_str = ""
        if use_web_search:
            with st.spinner("🔍 Caut cele mai noi ghiduri (2024-2025)..."):
                # Aici apelăm funcția modificată care adaugă automat anul curent
                search_res = search_tavily(final_prompt[:400])
                if search_res:
                    web_context_str = f"CONTEXT WEB RECENT (Surse):\n{search_res}\n"
        
        patient_block = ""
        if use_patient_mode:
            safe_context = st.session_state.patient_context[:6000] if st.session_state.patient_context else "Fără text extras."
            patient_block = f"""
            --- DATE PACIENT ---
            Gen: {gender}, Vârstă: {age} ani, Greutate: {weight} kg
            DOSAR MEDICAL: {safe_context}
            """
        
        history_str = ""
        for m in st.session_state.messages[-5:-1]: 
            role_label = "MEDIC" if m["role"] == "user" else "AI"
            history_str += f"{role_label}: {m['content']}\n"

        # 2. SYSTEM PROMPT UPDATE: Instruim AI-ul să verifice data
        current_date_str = datetime.datetime.now().strftime('%d %B %Y')
        instructions = f"""
        Ești un Consultant Medical Senior AI.
        DATA CURENTĂ: {current_date_str}.
        
        REGULI STRICTE:
        1. Caută PRIORITAR informații din anii 2024 și 2025.
        2. Dacă în CONTEXT WEB apar ghiduri vechi (ex: 2016) și unele noi (2023-2025), ignoră-le pe cele vechi.
        3. Dacă sursele sunt vechi, menționează explicit: "Bazat pe ghidurile din [AN]".
        4. Răspunde concis, medical.
        """
        
        full_prompt = f"{instructions}\n\n--- ISTORIC ---\n{history_str}\n\n{web_context_str}\n\n{patient_block}\n\n--- ÎNTREBARE ---\nMEDIC: {final_prompt}"

        try:
            with st.spinner("Analizez sursele..."):
                content_parts = [full_prompt]
                
                if use_patient_mode and st.session_state.images_context:
                    content_parts.extend(st.session_state.images_context)
                
                response = model.generate_content(content_parts)
                response_text = response.text
                
                final_html = format_links(response_text)
                response_placeholder.markdown(final_html, unsafe_allow_html=True)
                
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                
        except Exception as e:
            st.error("Eroare generare.")
            st.code(str(e))
