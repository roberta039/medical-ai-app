import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from PIL import Image
import re # Am adăugat biblioteca pentru procesarea textului

# --- CONFIGURARE ---
st.set_page_config(page_title="MediChat Pro + Linkuri", page_icon="🩺", layout="wide")

# Configurare API Key
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
except:
    st.error("⚠️ Cheia API lipsește! Seteaz-o în Streamlit Secrets.")

# --- SELECTARE MODEL (Versiunea Stabilă) ---
try:
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    active_model_name = "Gemini 2.0 Flash (Exp)"
except:
    model = genai.GenerativeModel('gemini-1.5-flash')
    active_model_name = "Gemini 1.5 Flash (Stabil)"

# --- FUNCȚIE SPECIALĂ PENTRU LINK-URI ÎN TAB NOU ---
def format_links_new_tab(text):
    """
    Caută link-urile Markdown [Text](URL) și le transformă în HTML
    cu target="_blank" pentru a se deschide în pagină nouă.
    """
    # Pattern pentru link-uri Markdown: [Text](URL)
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    
    # Funcție de înlocuire
    def replace_link(match):
        link_text = match.group(1)
        link_url = match.group(2)
        # Returnăm HTML cu target="_blank"
        return f'<a href="{link_url}" target="_blank" style="color: #0068c9; text-decoration: none; font-weight: bold;">{link_text} 🔗</a>'
    
    # Înlocuim în text
    new_text = re.sub(pattern, replace_link, text)
    return new_text

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
    st.caption(f"Engine: {active_model_name}")
    st.markdown("---")
    
    use_patient_data = st.toggle("Mod: Caz Clinic Pacient", value=False)
    
    if use_patient_data:
        st.info("Completează datele")
        gender = st.selectbox("Sex", ["Masculin", "Feminin"])
        age = st.number_input("Vârstă", value=30)
        weight = st.number_input("Greutate (kg)", value=70.0)
        
        uploaded_files = st.file_uploader("Dosar (PDF/Foto)", type=['pdf', 'png', 'jpg'], accept_multiple_files=True)
        
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
                    st.success("Date citite!")
    else:
        st.info("Mod: General")
        st.caption("AI-ul va genera link-uri către ghiduri.")
        st.session_state.patient_context = ""
        st.session_state.images_context = []

# --- CHAT AREA ---
st.subheader("Asistent Medical AI")

# Afișare mesaje (Aici aplicăm și formatarea link-urilor pentru istoric)
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        # Dacă e mesaj de la asistent, îl procesăm pentru link-uri
        if message["role"] == "assistant":
            formatted_content = format_links_new_tab(message["content"])
            st.markdown(formatted_content, unsafe_allow_html=True)
        else:
            st.markdown(message["content"])

if prompt := st.chat_input("Scrie întrebarea..."):
    
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Caut informații și link-uri..."):
            try:
                # PROMPT PENTRU FORMAT LINK-URI
                sources_request = """
                CERINȚE OBLIGATORII PENTRU SURSE:
                1. Include link-uri către ghiduri (ESC, AHA, MS.ro, etc).
                2. FOARTE IMPORTANT: Formatează link-urile STRICT în format Markdown: [Nume Sursă](URL_COMPLET).
                3. Exemplu corect: [Ghid ESC 2023](https://www.escardio.org/Guidelines)
                4. Nu pune URL-ul simplu, pune-l mereu în paranteze ca mai sus.
                """

                if use_patient_data:
                    system_prompt = f"""
                    Ești un asistent medical expert.
                    DATE PACIENT: Sex: {gender}, Vârstă: {age}, Greutate: {weight}kg.
                    DOSAR: {st.session_state.patient_context}
                    
                    {sources_request}
                    
                    Răspunde aplicat pe caz.
                    """
                    content_parts = [system_prompt, prompt]
                    if st.session_state.images_context:
                        content_parts.extend(st.session_state.images_context)
                else:
                    system_prompt = f"""
                    Ești un asistent medical expert. Răspunde la întrebări generale.
                    {sources_request}
                    """
                    content_parts = [system_prompt, prompt]

                # Generare
                response = model.generate_content(content_parts)
                
                # Procesăm textul primit ca să transformăm link-urile în HTML cu New Tab
                final_html_text = format_links_new_tab(response.text)
                
                # Afișăm folosind HTML (unsafe_allow_html=True este necesar pentru target="_blank")
                st.markdown(final_html_text, unsafe_allow_html=True)
                
                # Salvăm textul original (Markdown) în istoric, îl procesăm doar la afișare
                st.session_state.messages.append({"role": "assistant", "content": response.text})

            except Exception as e:
                st.error(f"Eroare: {e}")
