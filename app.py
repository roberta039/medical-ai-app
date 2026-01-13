import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image

# --- CONFIGURARE ---
st.set_page_config(page_title="MediChat 2.0 Hybrid", page_icon="⚡", layout="wide")

# Configurare API Key
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("⚠️ Cheia API lipsește! Seteaz-o în Streamlit Secrets.")

# Model Gemini 2.5 Flash (sau fallback la 1.5)
try:
    model = genai.GenerativeModel('gemini-2.5-flash')
except:
    model = genai.GenerativeModel('gemini-1.5-flash')

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
    # Dacă e OFF, ignorăm datele. Dacă e ON, le folosim.
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
        st.caption("Pune întrebări teoretice, despre ghiduri sau medicamente, fără a implica un pacient anume.")
        # Resetăm contextul dacă trecem pe general
        st.session_state.patient_context = ""
        st.session_state.images_context = []

# --- ZONA DE CHAT ---
st.title("⚡ MediChat 2.0")

if not use_patient_data:
    st.caption("💡 Ești în modul **General**. Întreabă orice despre medicină.")
else:
    st.caption(f"💡 Ești în modul **Pacient** ({gender}, {age} ani, {weight}kg).")

# Afișare mesaje
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input utilizator
if prompt := st.chat_input("Scrie întrebarea..."):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analizez..."):
            try:
                # CONSTRUIREA PROMPTULUI DINAMIC
                if use_patient_data:
                    # Modul PACIENT SPECIFIC
                    system_prompt = f"""
                    Ești un asistent medical expert (Gemini 2.0).
                    Răspunzi unui medic despre un caz specific.
                    
                    DATE PACIENT:
                    - Sex: {gender}
                    - Vârstă: {age} ani
                    - Greutate: {weight} kg
                    
                    CONTEXT DIN DOSAR (dacă există):
                    {st.session_state.patient_context}
                    
                    SARCINĂ:
                    Răspunde la întrebare ținând cont strict de datele pacientului de mai sus (ex: doze ajustate la greutate/vârstă, contraindicații la sex).
                    """
                    content_parts = [system_prompt, prompt]
                    if st.session_state.images_context:
                        content_parts.extend(st.session_state.images_context)
                        
                else:
                    # Modul GENERAL
                    system_prompt = """
                    Ești un asistent medical expert (Gemini 2.0).
                    Răspunzi unui medic la întrebări generale.
                    
                    SARCINĂ:
                    Oferă informații bazate pe ghiduri clinice, studii și farmacologie.
                    NU inventa date despre pacienți. Răspunde teoretic și la obiect.
                    """
                    content_parts = [system_prompt, prompt]

                # Generare
                response = model.generate_content(content_parts)
                
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                st.error(f"Eroare: {e}")
