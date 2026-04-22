import streamlit as st
import requests
import os
import json

# --- Page Configuration ---
st.set_page_config(
    page_title="Agentic AI Platform",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom Styling ---
st.markdown("""
    <style>
    .status-card {
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #e0e0e0;
        margin-bottom: 10px;
        background-color: #f9f9f9;
    }
    .status-online { border-left: 5px solid #28a745; }
    .status-offline { border-left: 5px solid #dc3545; }
    .status-label { font-weight: bold; font-size: 0.9em; color: #555; }
    .status-value { font-size: 1.1em; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- Configuration ---
AGENT_API_URL = os.getenv("AGENT_API_URL", "http://agent-core:8000")
N8N_URL = os.getenv("N8N_DASHBOARD_URL", "http://localhost:5678")

# --- Title & Header ---
st.title("🤖 Agentic AI Platform")
st.markdown("---")

# --- Sidebar / System Status ---
with st.sidebar:
    st.header("⚙️ System Status")
    
    def check_status(url, name):
        try:
            res = requests.get(f"{url}/health", timeout=2)
            if res.status_code == 200:
                return True
        except:
            pass
        return False

    # Status Indicators
    statuses = [
        {"name": "🧠 Ollama LLM (Llama 3.2)", "url": AGENT_API_URL, "label": "Integrated"},
        {"name": "📉 LangGraph Agentic", "url": AGENT_API_URL, "label": "Workflow Active"},
        {"name": "🗄️ RAG (PGVector)", "url": AGENT_API_URL, "label": "Knowledge Base"},
        {"name": "⚡ Redis SemanticCache", "url": AGENT_API_URL, "label": "Cache Layer"},
        {"name": "🔗 n8n Workflow", "url": AGENT_API_URL, "label": "Engine"},
    ]

    for s in statuses:
        is_online = check_status(s['url'], s['name'])
        status_class = "status-online" if is_online else "status-offline"
        status_text = "ONLINE" if is_online else "OFFLINE"
        
        st.markdown(f"""
            <div class="status-card {status_class}">
                <div class="status-label">{s['name']}</div>
                <div class="status-value" style="color: {'#28a745' if is_online else '#dc3545'}">{s['label']}: {status_text}</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.link_button("🌐 Open n8n Dashboard", N8N_URL)

# --- Chat Interface ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# User Input
if prompt := st.chat_input("Apa yang bisa saya bantu hari ini?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Berpikir..."):
            try:
                # NAIKKAN TIMEOUT JADI 120 DETIK
                response = requests.post(
                    f"{AGENT_API_URL}/chat",
                    json={"message": prompt, "thread_id": "streamlit-session"},
                    timeout=120
                )
                if response.status_code == 200:
                    data = response.json()
                    res_content = data.get("response", "Maaf, saya tidak mendapatkan jawaban.")
                    st.markdown(res_content)
                    st.session_state.messages.append({"role": "assistant", "content": res_content})
                else:
                    st.error(f"Error dari server: {response.status_code}")
            except Exception as e:
                st.error(f"Koneksi terputus atau timeout: {str(e)}")
