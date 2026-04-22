import os
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import CharacterTextSplitter
from langchain_community.vectorstores import PGVector
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from dotenv import load_dotenv

load_dotenv()

# Database connection string
# Note: Use 'localhost' if running script from host, or 'postgres' if running inside docker
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
DB_HOST = os.getenv("POSTGRES_HOST", "postgres") # Default to 'postgres' for docker
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "agent_db")

CONNECTION_STRING = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
COLLECTION_NAME = "internal_knowledge"

def ingest_data():
    # 1. Load data
    current_dir = os.path.dirname(os.path.abspath(__file__))
    knowledge_path = os.path.join(current_dir, "knowledge.txt")
    
    if not os.path.exists(knowledge_path):
        print(f"❌ File {knowledge_path} tidak ditemukan!")
        return
    
    print(f"📄 Loading knowledge from: {knowledge_path}")
    loader = TextLoader(knowledge_path)
    documents = loader.load()
    
    # 2. Split text
    text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    docs = text_splitter.split_documents(documents)
    
    # 3. Embedding (FastEmbed - Local & Lightweight)
    print("🧠 Memuat model embedding (FastEmbed)...")
    embeddings = FastEmbedEmbeddings()
    
    # 4. Ingest to PGVector
    print(f"🔄 Mensinkronisasi database dengan {len(docs)} potongan teks ke PGVector...")
    
    try:
        db = PGVector.from_documents(
            embedding=embeddings,
            documents=docs,
            collection_name=COLLECTION_NAME,
            connection_string=CONNECTION_STRING,
            pre_delete_collection=True # Cleans up old data before ingesting
        )
        print("✅ Sinkronisasi Selesai ke PGVector!")
    except Exception as e:
        print(f"❌ Terjadi kesalahan saat ingest: {str(e)}")
        print("💡 Pastikan Docker Postgres sudah berjalan dan pgvector extension aktif.")

if __name__ == "__main__":
    ingest_data()