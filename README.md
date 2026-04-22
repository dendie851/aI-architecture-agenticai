# Agentic AI Architecture Stack

This repository contains a full-stack Docker Compose setup for the Agentic AI design provided.

## Architecture Components
- **Front-End**: Streamlit (User Interface)
- **Agentic Core**: Python/FastAPI (LangGraph logic)
- **Orchestration**: n8n (Workflow engine for tools like Gmail/Calendar)
- **Database**: PostgreSQL with `pgvector` (Vector Database + User Data)
- **State Store**: Redis (Session & Thread management)
- **Local LLM**: Ollama (Pre-configured for Llama 3)

## Prerequisites
- Docker & Docker Compose
- (Optional) OpenAI API Key for GPT-4o usage

## Getting Started
1. **Clone and Configure**:
   ```bash
   cp .env.example .env
   # Edit .env with your OpenAI API Key if needed
   ```

2. **Run the Stack**:
   ```bash
   docker-compose up -d
   ```

3. **Access Services**:
   - **Frontend**: [http://localhost:8501](http://localhost:8501)
   - **n8n**: [http://localhost:5678](http://localhost:5678)
   - **Agent API**: [http://localhost:8000](http://localhost:8000)
   - **Ollama**: [http://localhost:11434](http://localhost:11434)

## Pulling the Model (DeepSeek)
Once the stack is running, you can pull the small DeepSeek model into Ollama:
```bash
docker exec -it agentic-llm ollama pull deepseek-r1:1.5b
```
