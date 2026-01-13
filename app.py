import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image

# --- CONFIGURARE ---
st.set_page_config(page_title="MediChat Pro + Surse", page_icon="🩺", layout="wide")

# Configurare API Key
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("⚠️ Cheia API lipsește! Seteaz-o în Streamlit Secrets.")

# --- CONFIGURARE MODEL CU GOOGLE SEARCH ---
# Activăm unelta de căutare pentru a primi link-uri reale
tools_configuration = [
    {"google_search": {}}
]

try:
    # Încercăm modelul experimental 2.0 cu Search activat
    model = genai.GenerativeModel(
        'gemini-2.0-flash-exp', 
        tools=tools_configuration
    )
except:
    # Fallback la 1.5 Flash cu Search activat
    model = genai.GenerativeModel(
        'gemini-1.5-flash',
        tools=tools_configuration
    )

# --- INITIALIZARE STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "patient_context" not in st.session_state:
    st.session_state.patient_context = ""
if "images_context" not in st.session_state:
    st.session_state.images_context = []

# --- SIDEBAR (BARA LATERALĂ) ---
with st.sidebar:
    st.title("⚙️ Setări Consult")
    
    # COMUTATOR PRINCIPAL
    use_patient_data = st.toggle("Activează Context Pacient", value=False)
    
    if use_patient_data:
        st.success("🟢 Mod: Cazul Specific")
        st.markdown("---")
        st.subheader("👤 Date Pacient")
        gender = st.selectbox("Sex", ["Masculin", "Feminin"])
        age = st.number_input("Vârstă", value=30)
        weight = st.number_input("Greutate (kg)", value=70.0)
        
        st.markdown("---")
        st.subheader("📂 Analize & Dosar")
        uploaded_files = st.file_uploader("Încarcă fișiere", type=['pdf', 'png', 'jpg'], accept_multiple_files=True)
        
        if st.button("Procesează Fișierele"):
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
                    st.success("Fișiere analizate!")
            else:
                st.warning("Nu ai selectat fișiere.")
    else:
        st.info("🔵 Mod: Întrebări Generale")
        st.caption("Pune întrebări teoretice. AI-ul va căuta surse pe internet.")
        st.session_state.patient_context = ""
        st.session_state.images_context = []

# --- ZONA DE CHAT ---
st.title("⚡ MediChat 2.0 + Surse")

if not use_patient_data:
    st.caption("💡 Mod **General**. Voi căuta link-uri relevante pentru răspunsuri.")
else:
    st.caption(f"💡 Mod **Pacient** ({gender}, {age} ani). Analizez cazul specific.")

# Afișare mesaje
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input utilizator
if prompt := st.chat_input("Scrie întrebarea (ex: Protocol tratament HTA ghid ESC)"):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Caut în literatura medicală (Google)..."):
            try:
                # --- PROMPT DESIGN PENTRU SURSE ---
                sources_instruction = """
                IMPORTANT:
                1. Folosește Google Search pentru a verifica informația.
                2. La finalul răspunsului, include o secțiune "📚 Bibliografie & Link-uri".
                3. Oferă LINK-uri (URL) directe și funcționale către ghiduri (ESC, AHA, NICE), articole PubMed sau site-uri oficiale.
                4. Nu inventa link-uri.
                """

                if use_patient_data:
                    # Modul PACIENT SPECIFIC
                    system_prompt = f"""
                    Ești un asistent medical expert.
                    {sources_instruction}
                    
                    DATE PACIENT:
                    - Sex: {gender}
                    - Vârstă: {age} ani
                    - Greutate: {weight} kg
                    
                    CONTEXT DIN DOSAR:
                    {st.session_state.patient_context}
                    
                    Răspunde aplicat pe caz, citând sursele care justifică decizia.
                    """
                    content_parts = [system_prompt, prompt]
                    if st.session_state.images_context:
                        content_parts.extend(st.session_state.images_context)
                        
                else:
                    # Modul GENERAL
                    system_prompt = f"""
                    Ești un asistent medical expert.
                    {sources_instruction}
                    
                    Răspunde teoretic, bazat pe dovezi (Evidence Based Medicine).
                    """
                    content_parts = [system_prompt, prompt]

                # Generare
                response = model.generate_content(content_parts)
                
                # Afișare răspuns
                st.markdown(response.text)
                
                # Afișare metadate despre căutarea Google (dacă există)
                # Uneori API-ul returnează sursele separat în metadata, le afișăm sub răspuns
                if response.candidates[0].grounding_metadata.search_entry_point:
                     st.caption("🔍 Sursă verificată prin Google Search Grounding")

                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                st.error(f"Eroare: {e}")
