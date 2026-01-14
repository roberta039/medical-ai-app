import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
from tavily import TavilyClient
import re
import datetime

# --- 1. CONFIGURARE PAGINĂ & STIL ---
st.set_page_config(page_title="MediChat AI Pro", page_icon="🩺", layout="wide")

# CSS: Stilizează link-urile și chat-ul
st.markdown("""
    <style>
    .stChatMessage { font-family: 'Arial', sans-serif; }
    .stButton button { width: 100%; border-radius: 8px; }
    div[data-baseweb="input"] { background-color: #f0f2f6; }
    /* Stil pentru link-uri în chat */
    a { text-decoration: none; font-weight: bold; color: #0066cc !important; }
    a:hover { text-decoration: underline; color: #004499 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DISCLAIMER ---
st.warning("⚠️ **PROTOTIP MEDICAL:** Verificați întotdeauna sursele oficiale. Link-urile sunt generate automat și trebuie validate.")

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
    """Găsește cel mai bun model Gemini disponibil."""
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
    st.error("❌ EROARE: Nu am putut încărca modelul AI.")
    st.stop()

def search_tavily(query):
    """Caută date recente și returnează titlu + URL."""
    try:
        # Forțăm ani recenți în query
        current_year = datetime.datetime.now().year
        optimized_query = f"{query} latest clinical guidelines medical research {current_year} {current_year-1}"
        
        response = tavily.search(
            query=optimized_query, 
            search_depth="advanced", 
            max_results=5, 
            include_domains=["nih.gov", "pubmed.ncbi.nlm.nih.gov", "escardio.org", "heart.org", "who.int", "medscape.com", "mayoclinic.org", "nejm.org", "thelancet.com", "uptodate.com"],
            topic="general"
        )
        context_text = ""
        # Construim un text clar pentru AI, astfel încât să știe ce link aparține cărui titlu
        for result in response['results']:
            context_text += f"SURSA_ID: {result['title']} || URL_EXACT: {result['url']} || TEXT: {result['content']}\n\n"
        return context_text
    except Exception as e:
        return ""

def format_links(text):
    """Transformă [Titlu](URL) în HTML <a href='URL'>Titlu 🔗</a>"""
    # Regex pentru markdown standard [text](url)
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
    txt = f"=== RAPORT MEDICAL ===\nData: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}\n\n"
    txt += f"Pacient: {gender}, {age} ani, {weight} kg\n"
    txt += "-" * 40 + "\n"
    for msg in messages:
        role = "MEDIC" if msg["role"] == "user" else "AI"
        content = msg["content"].replace("**", "")
        txt += f"\n[{role}]: {content}\n"
    return txt

# --- 5. STATE ---
if "messages" not in st.session_state: st.session_state.messages = []
if "patient_context" not in st.session_state: st.session_state.patient_context = ""
if "images_context" not in st.session_state: st.session_state.images_context = []

# --- 6. SIDEBAR ---
with st.sidebar:
    st.title("🩺 Control Panel")
    
    col1, col2 = st.columns(2)
    with col1: use_web_search = st.toggle("🌐 Internet", value=True)
    with col2: use_patient_mode = st.toggle("📂 Dosar", value=False)
    
    st.divider()
    
    gender_exp, age_exp, weight_exp = "N/A", "N/A", "N/A"
    if use_patient_mode:
        st.subheader("Date Pacient")
        gender = st.selectbox("Gen", ["Masculin", "Feminin"])
        age = st.number_input("Ani", value=45)
        weight = st.number_input("Kg", value=75.0)
        gender_exp, age_exp, weight_exp = gender, age, weight
        
        uploaded_files = st.file_uploader("PDF / Foto", type=['pdf', 'png', 'jpg'], accept_multiple_files=True)
        if uploaded_files:
            raw_text = ""
            images = []
            for file in uploaded_files:
                if file.type == "application/pdf":
                    try:
                        reader = PdfReader(file)
                        for page in reader.pages: raw_text += page.extract_text() + "\n"
                    except: pass
                else:
                    images.append(Image.open(file))
            st.session_state.patient_context = raw_text
            st.session_state.images_context = images
            if raw_text or images: st.success("✅ Date încărcate.")
    else:
        st.session_state.patient_context = ""
        st.session_state.images_context = []

    st.divider()
    if st.session_state.messages:
        report = generate_report_text(gender_exp, age_exp, weight_exp, st.session_state.patient_context, st.session_state.messages)
        st.download_button("📄 Descarcă Raport", report, f"Raport_{datetime.date.today()}.txt")
    if st.button("🗑️ Reset", type="primary"):
        st.session_state.messages = []
        st.rerun()

# --- 7. CHAT UI ---
st.subheader("💬 Asistent Medical")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            st.markdown(format_links(msg["content"]), unsafe_allow_html=True)
        else:
            st.markdown(msg["content"])

# --- 8. LOGICĂ & PROMPTING ---
audio_val = st.audio_input("🎤 Dictare")
voice_text = ""
if audio_val:
    with st.spinner("🎧 Transcriu..."):
        t = transcribe_audio(audio_val.read())
        if t: voice_text = t

user_input = st.chat_input("Întrebare...")
final_prompt = user_input if user_input else (voice_text if voice_text and audio_val else None)

if final_prompt:
    st.session_state.messages.append({"role": "user", "content": final_prompt})
    with st.chat_message("user"): st.markdown(final_prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        
        # SEARCH
        web_context_str = ""
        if use_web_search:
            with st.spinner("🔍 Caut surse 2024-2026..."):
                res = search_tavily(final_prompt[:400])
                if res: web_context_str = f"CONTEXT WEB (Conține linkuri reale):\n{res}\n"
        
        # PATIENT
        patient_block = ""
        if use_patient_mode:
            patient_block = f"PACIENT: {gender}, {age} ani, {weight}kg.\nDOSAR: {st.session_state.patient_context[:6000]}"
        
        # HISTORY
        history_str = ""
        for m in st.session_state.messages[-5:-1]:
            history_str += f"{'MEDIC' if m['role']=='user' else 'AI'}: {m['content']}\n"

        # SYSTEM PROMPT - Aici e cheia pentru link-uri
        current_date = datetime.datetime.now().strftime('%B %Y')
        system_prompt = f"""
        Ești un Asistent Medical Expert. DATA AZI: {current_date}.
        
        INSTRUCȚIUNI OBLIGATORII:
        1. Caută date din 2024-2026. Ignoră datele vechi dacă există altele noi.
        2. Răspunde structurat, cu bullet points.
        
        3. SURSE ȘI BIBLIOGRAFIE (FOARTE IMPORTANT):
           - Dacă ai folosit 'CONTEXT WEB', la finalul răspunsului ești OBLIGAT să adaugi o secțiune separată:
           ### 📚 Surse Verificate
           - Trebuie să listezi link-urile sub formatul Markdown:
             - [Titlu Sursă](URL_EXACT_DIN_CONTEXT)
           - NU inventa link-uri. Folosește doar URL-urile furnizate în context.
        
        --- CONTEXT WEB ---
        {web_context_str}
        
        --- DATE PACIENT ---
        {patient_block}
        
        --- ISTORIC ---
        {history_str}
        
        ÎNTREBARE: {final_prompt}
        """

        try:
            with st.spinner("Generez răspuns cu bibliografie..."):
                parts = [system_prompt]
                if use_patient_mode and st.session_state.images_context:
                    parts.extend(st.session_state.images_context)
                
                response = model.generate_content(parts)
                final_html = format_links(response.text)
                response_placeholder.markdown(final_html, unsafe_allow_html=True)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
        except Exception as e:
            st.error(f"Eroare: {e}")
