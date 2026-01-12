import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
import io

# --- CONFIGURARE ---
st.set_page_config(page_title="MediChat Pro", page_icon="🩺", layout="wide")

# Configurare API Key
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("⚠️ Cheia API lipsește! Seteaz-o în Streamlit Secrets.")

# Folosim Gemini 1.5 Flash pentru că știe să citească imagini și texte lungi
model = genai.GenerativeModel('gemini-1.5-flash')

# --- INTERFAȚA LATERALĂ (DATE PACIENT) ---
with st.sidebar:
    st.header("📋 Fișa Pacientului")
    st.info("Nu introduceți Nume/CNP! (GDPR)")
    
    # Input-uri structurate
    gender = st.selectbox("Sex", ["Masculin", "Feminin", "Altul"])
    age = st.number_input("Vârstă (ani)", min_value=0, max_value=120, value=30)
    weight = st.number_input("Greutate (kg)", min_value=0.0, max_value=300.0, value=70.0)
    
    st.markdown("---")
    st.subheader("📂 Documente & Analize")
    uploaded_files = st.file_uploader(
        "Încarcă PDF sau Imagini (JPG/PNG)", 
        type=['pdf', 'png', 'jpg', 'jpeg'], 
        accept_multiple_files=True
    )
    
    process_btn = st.button("Procesează Datele")

# --- FUNCȚII UTILITARE ---
def get_pdf_text(pdf_docs):
    text = ""
    for pdf in pdf_docs:
        pdf_reader = PdfReader(pdf)
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
    return text

# --- LOGICA PRINCIPALĂ ---
st.title("🩺 MediChat Pro - Analiză Cazuri Clinice")
st.warning("⚠️ DISCLAIMER: Instrument suport. Verificați întotdeauna rezultatele. AI-ul poate halucina.")

# Inițializare sesiune chat
if "messages" not in st.session_state:
    st.session_state.messages = []
if "patient_context" not in st.session_state:
    st.session_state.patient_context = ""
if "images_context" not in st.session_state:
    st.session_state.images_context = []

# Procesarea fișierelor când se apasă butonul
if process_btn and uploaded_files:
    with st.spinner("Se procesează dosarul medical..."):
        raw_text = ""
        images = []
        
        for file in uploaded_files:
            # Dacă e PDF, extragem textul
            if file.type == "application/pdf":
                reader = PdfReader(file)
                for page in reader.pages:
                    raw_text += page.extract_text() + "\n"
            
            # Dacă e Imagine, o pregătim pentru Gemini
            elif file.type in ["image/jpeg", "image/png", "image/jpg"]:
                image = Image.open(file)
                images.append(image)

        # Salvăm contextul
        st.session_state.patient_context = raw_text
        st.session_state.images_context = images
        st.success(f"Au fost procesate: {len(uploaded_files)} fișiere.")

# Afișare istoric chat
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input utilizator
if prompt := st.chat_input("Ex: Pe baza analizelor și a vârstei, care este diagnosticul diferențial?"):
    
    # Afișare mesaj user
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Construire prompt complex pentru AI
    with st.chat_message("assistant"):
        with st.spinner("Analizez cazul..."):
            try:
                # 1. Definirea "Personalității" AI-ului și a datelor structurate
                system_prompt = f"""
                Ești un consultant medical expert.
                
                DETALII PACIENT:
                - Sex: {gender}
                - Vârstă: {age} ani
                - Greutate: {weight} kg
                
                CONTEXT DIN DOCUMENTE ÎNCĂRCATE (Istoric/Analize text):
                {st.session_state.patient_context}
                
                INSTRUCȚIUNI:
                1. Analizează întrebarea medicului luând în calcul datele de mai sus.
                2. Dacă există imagini atașate, ia-le în considerare pentru context vizual.
                3. Răspunde structurat, profesional, în limba română.
                """

                # 2. Pregătirea listei de conținut pentru Gemini (Text + Imagini)
                content_parts = [system_prompt, prompt]
                
                # Adăugăm imaginile dacă există (Gemini Flash știe să se uite la ele)
                if st.session_state.images_context:
                    content_parts.extend(st.session_state.images_context)

                # 3. Generare răspuns
                response = model.generate_content(content_parts)
                
                st.markdown(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                st.error(f"Eroare: {e}. Încearcă să reformulezi sau să reduci numărul de fișiere.")
