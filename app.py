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
    /* Facem input-urile de numere mai vizibile */
    div[data-baseweb="input"] { background-color: #f0f2f6; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DISCLAIMER OBLIGATORIU ---
st.warning("⚠️ **AVERTISMENT MEDICAL:** Acest asistent AI este un prototip experimental. Răspunsurile pot fi inexacte. Verificați întotdeauna informațiile cu ghiduri clinice oficiale. Nu introduceți date personale care pot identifica pacienții (Nume, CNP).")

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
    """Caută pe site-uri medicale de încredere."""
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
            context_text += f"- SURSA: {result['title']}\n  URL: {result['url']}\n  INFO: {result['content']}\n\n"
        return context_text
    except Exception as e:
        return ""

def format_links(text):
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    return re.sub(pattern, r'<a href="\2" target="_blank" style="color: #0068c9; font-weight: bold;">\1 🔗</a>', text)

def transcribe_audio(audio_bytes):
    """Folosește Gemini pentru a transcrie audio în text medical."""
    try:
        prompt_transcribe = "Transcrede acest fișier audio exact în limba română. Este o întrebare medicală."
        response = model.generate_content([prompt_transcribe, {"mime_type": "audio/wav", "data": audio_bytes}])
        return response.text
    except Exception as e:
        return None

def generate_report_text(gender, age, weight, patient_context, messages):
    """Generează conținutul fișierului text pentru descărcare."""
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
        content = msg["content"].replace("**", "").replace("__", "") # Curățăm puțin markdown-ul
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
    
    # Butoane Generale
    col_set_1, col_set_2 = st.columns(2)
    with col_set_1:
        use_web_search = st.toggle("🌐 Internet", value=True, help="Activ: Caută studii online.")
    with col_set_2:
        use_patient_mode = st.toggle("📂 Dosar", value=False, help="Activează modul pacient specific.")

    st.divider()
    
    # Initialize variables for export
    gender_exp, age_exp, weight_exp = "N/A", "N/A", "N/A"

    if use_patient_mode:
        st.subheader("📝 Date Pacient")
        st.info("Introduceți detaliile pentru context.")
        
        # UI CLAR PENTRU DATE
        gender = st.selectbox("Gen / Sex", ["Masculin", "Feminin"], index=0)
        age = st.number_input("Vârstă (Ani)", min_value=0, max_value=120, value=45, step=1)
        weight = st.number_input("Greutate (Kg)", min_value=0.0, max_value=300.0, value=75.0, step=0.1, format="%.1f")
        
        # Variabile pentru export
        gender_exp, age_exp, weight_exp = gender, age, weight

        st.markdown("**Atașează Documente:**")
        uploaded_files = st.file_uploader("PDF Analize / Poze EKG, CT...", type=['pdf', 'png', 'jpg', 'jpeg'], accept_multiple_files=True)
        
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
                st.caption(f"✅ Sistem: {len(images)} imagini, {len(raw_text)} caractere text.")
    else:
        st.session_state.patient_context = ""
        st.session_state.images_context = []

    st.divider()
    
    # EXPORT RAPORT
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

# Afișare istoric
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            st.markdown(format_links(msg["content"]), unsafe_allow_html=True)
        else:
            st.markdown(msg["content"])

# --- 8. LOGICA DE INTRARE (VOCE SAU TEXT) ---

# A. Intrare Vocală
audio_val = st.audio_input("🎤 Apasă pentru a dicta o întrebare")
voice_text = ""

if audio_val:
    with st.spinner("🎧 Transcriu vocea..."):
        # Citim bytes din audio
        audio_bytes = audio_val.read()
        transcription = transcribe_audio(audio_bytes)
        if transcription:
            voice_text = transcription
        else:
            st.error("Nu s-a putut transcrie audio.")

# B. Intrare Text (sau textul transcris)
user_input = st.chat_input("Scrie întrebarea aici...")

# Determinăm care este promptul final (Voce sau Text)
final_prompt = None

if user_input:
    final_prompt = user_input
elif voice_text and audio_val: 
    # Folosim vocea doar daca s-a inregistrat ceva nou si nu s-a scris text
    # (Mecanism simplificat: ultimul trigger câștigă)
    final_prompt = voice_text

# --- 9. PROCESARE FINALĂ ---
if final_prompt:
    
    # Adăugăm în chat
    st.session_state.messages.append({"role": "user", "content": final_prompt})
    with st.chat_message("user"):
        st.markdown(final_prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        
        # Context Web
        web_context_str = ""
        if use_web_search:
            with st.spinner("🔍 Caut informații medicale actualizate..."):
                search_res = search_tavily(final_prompt[:400])
                if search_res:
                    web_context_str = f"CONTEXT WEB (Surse):\n{search_res}\n"
        
        # Context Pacient
        patient_block = ""
        if use_patient_mode:
            safe_context = st.session_state.patient_context[:6000] if st.session_state.patient_context else "Fără text extras."
            patient_block = f"""
            --- DATE PACIENT ---
            Gen: {gender}
            Vârstă: {age} ani
            Greutate: {weight} kg
            DOSAR MEDICAL: {safe_context}
            """
        
        # Context Istoric
        history_str = ""
        for m in st.session_state.messages[-5:-1]: 
            role_label = "MEDIC" if m["role"] == "user" else "AI"
            history_str += f"{role_label}: {m['content']}\n"

        # Instrucțiuni Sistem
        instructions = """
        Ești un Consultant Medical Senior AI.
        1. Răspunde concis, folosind terminologie medicală.
        2. Dacă primești CONTEXT WEB, citează sursele: [Sursa](URL).
        3. Dacă primești DATE PACIENT, interpretează-le specific.
        4. Dacă nu ai informații suficiente, recunoaște acest lucru.
        """
        
        full_prompt = f"{instructions}\n\n--- ISTORIC ---\n{history_str}\n\n{web_context_str}\n\n{patient_block}\n\n--- ÎNTREBARE ---\nMEDIC: {final_prompt}"

        # Generare
        try:
            with st.spinner("Generare răspuns..."):
                content_parts = [full_prompt]
                
                if use_patient_mode and st.session_state.images_context:
                    content_parts.extend(st.session_state.images_context)
                
                response = model.generate_content(content_parts)
                response_text = response.text
                
                final_html = format_links(response_text)
                response_placeholder.markdown(final_html, unsafe_allow_html=True)
                
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                
        except Exception as e:
            st.error("A apărut o eroare.")
            st.code(str(e))
