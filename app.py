import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
from tavily import TavilyClient
import re

# --- 1. CONFIGURARE PAGINĂ & STIL ---
st.set_page_config(page_title="MediChat AI Pro", page_icon="🩺", layout="wide")

# CSS pentru a face chat-ul mai lizibil
st.markdown("""
    <style>
    .stChatMessage { font-family: 'Arial', sans-serif; }
    .stButton button { width: 100%; border-radius: 8px; }
    div[data-testid="stToast"] { padding: 1rem; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DISCLAIMER OBLIGATORIU ---
st.warning("⚠️ **AVERTISMENT MEDICAL:** Acest asistent AI este un prototip experimental. Răspunsurile pot fi inexacte sau halucinate. Verificați întotdeauna informațiile cu ghiduri clinice oficiale. Nu introduceți date personale care pot identifica pacienții (Nume, CNP, Adresă).")

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
        
        # Prioritate: Flash (rapid) -> Pro (complex) -> Orice altceva
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
    """Transformă linkurile markdown în linkuri HTML care se deschid în tab nou."""
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    return re.sub(pattern, r'<a href="\2" target="_blank" style="color: #0068c9; font-weight: bold;">\1 🔗</a>', text)

# --- 5. GESTIONARE STARE (SESSION STATE) ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "patient_context" not in st.session_state:
    st.session_state.patient_context = ""
if "images_context" not in st.session_state:
    st.session_state.images_context = []

# --- 6. SIDEBAR (CONTROALE) ---
with st.sidebar:
    st.title("🩺 Control Panel")
    st.caption(f"Model activ: `{model_name.split('/')[-1]}`")
    
    st.markdown("### ⚙️ Setări Asistent")
    
    # BUTONUL CERUT: Activare/Dezactivare Internet
    use_web_search = st.toggle("🌐 Căutare Web (Tavily)", value=True, help="Dacă este activat, AI-ul va căuta cele mai recente studii/ghiduri. Dacă e oprit, răspunde doar din cunoștințele interne.")
    
    st.markdown("---")
    
    # MODUL CAZ CLINIC
    use_patient_mode = st.toggle("📂 Mod: Caz Clinic (Date Pacient)", value=False)
    
    if use_patient_mode:
        st.info("📝 Introdu datele anonimizate ale pacientului.")
        c1, c2, c3 = st.columns(3)
        with c1: gender = st.selectbox("Sex", ["M", "F"], label_visibility="collapsed")
        with c2: age = st.number_input("Ani", value=45, label_visibility="collapsed")
        with c3: weight = st.number_input("Kg", value=75, label_visibility="collapsed")
        
        uploaded_files = st.file_uploader("Analize (PDF) sau Imagistică (Foto)", type=['pdf', 'png', 'jpg', 'jpeg'], accept_multiple_files=True)
        
        if uploaded_files:
            # Procesare automată la upload
            raw_text = ""
            images = []
            for file in uploaded_files:
                if file.type == "application/pdf":
                    try:
                        reader = PdfReader(file)
                        for page in reader.pages:
                            raw_text += page.extract_text() + "\n"
                    except:
                        st.error("Eroare la citirea PDF-ului.")
                else:
                    images.append(Image.open(file))
            
            st.session_state.patient_context = raw_text
            st.session_state.images_context = images
            if raw_text or images:
                st.success(f"✅ Dosar încărcat: {len(images)} imagini, {len(raw_text)} caractere text.")
    else:
        # Curățăm contextul dacă se iese din modul pacient
        st.session_state.patient_context = ""
        st.session_state.images_context = []

    st.markdown("---")
    if st.button("🗑️ Șterge Conversația", type="primary"):
        st.session_state.messages = []
        st.rerun()

# --- 7. INTERFAȚA DE CHAT ---
st.subheader("💬 Discuție Medicală")

# Afișare istoric
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            st.markdown(format_links(msg["content"]), unsafe_allow_html=True)
        else:
            st.markdown(msg["content"])

# --- 8. LOGICA DE PROCESARE (THE BRAIN) ---
if prompt := st.chat_input("Întreabă despre un tratament, un diagnostic sau datele pacientului..."):
    
    # Adăugăm mesajul utilizatorului în istoric
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        
        # A. Căutare Web (Doar dacă butonul este activat)
        web_context_str = ""
        if use_web_search:
            with st.spinner("🔍 Caut informații medicale actualizate..."):
                search_res = search_tavily(prompt[:400])
                if search_res:
                    web_context_str = f"CONTEXT WEB (Surse Externe):\n{search_res}\n"
        
        # B. Construire Context Pacient
        patient_block = ""
        if use_patient_mode:
            # Limităm contextul pentru a evita erorile de prea mult text
            safe_context = st.session_state.patient_context[:5000] if st.session_state.patient_context else "Nu există text extras."
            patient_block = f"""
            --- DATE PACIENT CURENT ---
            Sex: {gender}, Vârstă: {age}, Greutate: {weight}kg.
            REZUMAT DOSAR/ANALIZE: {safe_context} 
            (Notă: Dacă există imagini atașate, analizează-le vizual).
            """
        
        # C. Construire Memorie (Istoric Conversație)
        history_str = ""
        # Luăm ultimele 5 mesaje
        for m in st.session_state.messages[-6:-1]: 
            role_label = "MEDIC" if m["role"] == "user" else "AI"
            history_str += f"{role_label}: {m['content']}\n"

        # D. Promptul de Sistem - DEFINIT CU ATENȚIE
        # Folosim concatenare simplă pentru a evita erorile de sintaxă la copy-paste
        base_instruction = """
        Ești un Consultant Medical Senior AI. Discuți cu un coleg medic.
        SARCINI:
        1. Răspunde concis, profesional și la obiect.
        2. Folosește terminologie medicală adecvată.
        3. Dacă primești CONTEXT WEB, folosește-l prioritar și citează sursele [Sursa](URL).
        4. Dacă primești DATE PACIENT, interpretează-le specific pentru acest caz.
        """
        
        # Asamblăm promptul final
        final_prompt = f"{base_instruction}\n\n--- ISTORIC CONVERSAȚIE ---\n{history_str}\n\n{web_context_str}\n\n{patient_block}\n\n--- ÎNTREBARE CURENTĂ ---\nMEDIC: {prompt}"

        # E. Apelarea Modelului
        try:
            with st.spinner("Generare răspuns..."):
                content_parts = [final_prompt]
                
                # Dacă avem imagini și suntem în mod pacient, le trimitem modelului
                if use_patient_mode and st.session_state.images_context:
                    content_parts.extend(st.session_state.images_context)
                
                response = model.generate_content(content_parts)
                response_text = response.text
                
                # Afișare
                final_html = format_links(response_text)
                response_placeholder.markdown(final_html, unsafe_allow_html=True)
                
                # Salvare în istoric
                st.session_state.messages.append({"role": "assistant", "content": response_text})
                
        except Exception as e:
            st.error(f"Eroare la generare: {str(e)}")
            st.info("Sfat: Încearcă să reformulezi sau să dezactivezi temporar căutarea web.")
