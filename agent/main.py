from typing import Annotated, TypedDict, Union
from fastapi import FastAPI, Body
from contextlib import asynccontextmanager
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_community.vectorstores import PGVector
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
import os
import requests
import json
import redis
import re
import logging
import numpy as np
from uuid import uuid4

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-core")

# --- Configuration ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password@postgres:5432/agent_db")
CONNECTION_STRING = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1) if DATABASE_URL.startswith("postgresql://") else DATABASE_URL
COLLECTION_NAME = "internal_knowledge"
EMAIL_WEBHOOK = "http://n8n:5678/webhook/send-email-tool"
WA_WEBHOOK = "http://n8n:5678/webhook/send-wa-tool"
REDIS_HOST = os.getenv("REDIS_HOST", "agentic-state")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# --- Redis & Embeddings Setup ---
embeddings_model = FastEmbedEmbeddings()
_redis_client = None

def get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, socket_timeout=5)
            _redis_client.ping()
        except: _redis_client = None
    return _redis_client

# --- Tools Definition ---

@tool
def knowledge_base_tool(query: str):
    """Cari info produk dan harga."""
    try:
        vectorstore = PGVector(connection_string=CONNECTION_STRING, collection_name=COLLECTION_NAME, embedding_function=embeddings_model)
        docs = vectorstore.similarity_search(query, k=2)
        return "\n".join([d.page_content for d in docs]) if docs else "Data tidak ditemukan."
    except: return "Database sibuk."

@tool
def email_tool(recipient: str, body: str, subject: str = "Info Penawaran Produk"):
    """Kirim email."""
    try:
        requests.post(EMAIL_WEBHOOK, json={"recipient": recipient, "subject": subject, "body": body}, timeout=5)
        return "SUCCESS"
    except: return "FAILED"

@tool
def whatsapp_tool(recipient: str, message: str):
    """Kirim WhatsApp."""
    try:
        requests.post(WA_WEBHOOK, json={"recipient": recipient, "message": message}, timeout=5)
        return "SUCCESS"
    except: return "FAILED"

tools = [knowledge_base_tool, email_tool, whatsapp_tool]
tool_map = {t.name: t for t in tools}

# --- Agentic Core Setup ---

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def get_llm():
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and openai_key.startswith("sk-") and len(openai_key) > 20:
        return ChatOpenAI(model="gpt-4o").bind_tools(tools)
    return ChatOllama(model=os.getenv("OLLAMA_MODEL", "llama3.2:1b"), base_url=os.getenv("OLLAMA_HOST", "http://ollama:11434"), temperature=0.1, num_predict=256).bind_tools(tools)

def call_model(state: AgentState):
    llm = get_llm()
    messages = state['messages']
    
    if not messages:
        return {"messages": [AIMessage(content="Halo, ada yang bisa saya bantu?")]}

    last_msg = messages[-1]
    
    # Check for tool success
    if isinstance(last_msg, ToolMessage):
        if last_msg.content == "SUCCESS":
            return {"messages": [AIMessage(content="✅ Berhasil! Informasi sudah saya kirimkan.")]}
        elif last_msg.content == "FAILED":
            return {"messages": [AIMessage(content="❌ Maaf, pengiriman gagal.")]}

    last_user_msg = last_msg.content if isinstance(last_msg, HumanMessage) else ""
    query_lower = last_user_msg.lower()
    
    # Ambil konteks informasi terakhir (AI message)
    context_info = ""
    for m in reversed(messages):
        # Abaikan pesan "Mengirim..." atau "Mencari..."
        if isinstance(m, AIMessage) and m.content and len(m.content) > 20 and "..." not in m.content:
            context_info = m.content
            break

    # Short-Circuit logic
    if "@" in query_lower and ("kirim" in query_lower or "email" in query_lower):
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', last_user_msg)
        if email_match:
            body_content = f"Informasi yang Anda minta:\n\n{context_info}" if context_info else last_user_msg
            return {"messages": [AIMessage(content=f"Mengirim email ke {email_match.group(0)}...", tool_calls=[{"name": "email_tool", "args": {"recipient": email_match.group(0), "body": body_content}, "id": f"call_{uuid4().hex}"}])] }
            
    elif ("wa" in query_lower or "whatsapp" in query_lower) and "kirim" in query_lower:
        phone_match = re.search(r'\d{10,15}', last_user_msg)
        if phone_match:
            wa_content = f"Halo, berikut info produknya:\n\n{context_info}" if context_info else last_user_msg
            return {"messages": [AIMessage(content=f"Mengirim WA ke {phone_match.group(0)}...", tool_calls=[{"name": "whatsapp_tool", "args": {"recipient": phone_match.group(0), "message": wa_content}, "id": f"call_{uuid4().hex}"}])] }
    
    elif any(kw in query_lower for kw in ["harga", "biaya", "paket", "produk"]):
         return {"messages": [AIMessage(content="Mencari info...", tool_calls=[{"name": "knowledge_base_tool", "args": {"query": last_user_msg}, "id": f"call_{uuid4().hex}"}])] }

    try:
        response = llm.invoke([{"role": "system", "content": "Jawab singkat menggunakan data RAG."}] + messages[-5:])
        if not response.content: response.content = " "
        return {"messages": [response]}
    except: return {"messages": [AIMessage(content="Sedang memproses...")]}

def route_tools(state: AgentState):
    last_msg = state['messages'][-1]
    return "tools" if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls else END

def call_tools(state: AgentState):
    last_message = state['messages'][-1]
    tool_messages = []
    for tool_call in last_message.tool_calls:
        name, args = tool_call['name'], tool_call['args']
        if name == "knowledge_base_tool" and "query" not in args: args = {"query": list(args.values())[0] if args else "harga"}
        if name in tool_map:
            output = tool_map[name].invoke(args)
            tool_messages.append(ToolMessage(tool_call_id=tool_call['id'], content=str(output)))
    return {"messages": tool_messages}

workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", call_tools)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", route_tools, {"tools": "tools", END: END})
workflow.add_edge("tools", "agent")

app_graph = None
@asynccontextmanager
async def lifespan(app: FastAPI):
    global app_graph
    async with AsyncConnectionPool(conninfo=DATABASE_URL, kwargs={"autocommit": True, "prepare_threshold": 0}, max_size=10, open=True) as pool:
        app_graph = workflow.compile(checkpointer=AsyncPostgresSaver(pool))
        await app_graph.checkpointer.setup()
        yield

app = FastAPI(title="Agentic AI Core", lifespan=lifespan)

# --- SEMANTIC CACHE LOGIC ---
def find_semantic_cache(query: str):
    r = get_redis()
    if not r: return None
    try:
        # DETEKSI JANGAN CACHE PERINTAH KIRIM
        ql = query.lower()
        if "kirim" in ql or "@" in ql or "wa" in ql: return None
        
        query_vector = np.array(embeddings_model.embed_query(query), dtype=np.float32).tobytes()
        keys = r.keys("semcache:*")
        for k in keys:
            cache_data = json.loads(r.get(k))
            stored_vector = np.array(cache_data['vector'], dtype=np.float32)
            current_vector = np.frombuffer(query_vector, dtype=np.float32)
            similarity = np.dot(stored_vector, current_vector) / (np.linalg.norm(stored_vector) * np.linalg.norm(current_vector))
            if similarity > 0.95:
                return cache_data['response']
    except Exception as e:
        logger.error(f"Semantic Cache Error: {str(e)}")
    return None

@app.post("/chat")
async def chat(message: str = Body(..., embed=True), thread_id: str = "default-session"):
    if not app_graph: return {"error": "..."}
    config = {"configurable": {"thread_id": thread_id}}
    
    cached_res = find_semantic_cache(message)
    if cached_res:
        logger.info(f"🎯 Cache Hit! Updating state for {thread_id}")
        # Gunakan ainvoke dengan pesan kosong untuk memicu update state secara resmi
        await app_graph.aupdate_state(config, {"messages": [HumanMessage(content=message), AIMessage(content=cached_res)]})
        return {"response": cached_res}

    try:
        # Gunakan ainvoke standar
        result = await app_graph.ainvoke({"messages": [HumanMessage(content=message)]}, config=config)
        res = result['messages'][-1].content
        res = re.sub(r'\{.*\}', '', str(res), flags=re.DOTALL).strip()
        
        if not res or "Mengirim" in res or "Mencari" in res:
            for m in reversed(result['messages']):
                if isinstance(m, AIMessage) and m.content and len(m.content) > 20 and "..." not in m.content: 
                    res = m.content
                    break
        
        if not res or len(res) < 5: res = "Proses selesai."
        
        # Simpan ke cache jika jawaban berkualitas
        r = get_redis()
        if r and len(res) > 30 and "kirim" not in message.lower():
            try:
                vector = embeddings_model.embed_query(message)
                r.setex(f"semcache:{uuid4().hex}", 3600, json.dumps({"response": res, "vector": vector}))
            except: pass
            
        return {"response": res}
    except Exception as e:
        logger.error(f"Chat Error: {str(e)}")
        return {"error": "Maaf, terjadi kesalahan."}

@app.get("/health")
async def health(): return {"status": "healthy"}
