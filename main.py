import os
from dotenv import load_dotenv
from graph import RAGAgent, rag_app, lead_gen_node, res
from tools import extract_text_from_docx, extract_text_from_pdf, get_openai_client

load_dotenv()

base_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(base_dir, "Knowledge", "Prospectus.docx")

rag_state = {
    "file_path": file_path
}

def initialize_knowledge_base():
    client = get_openai_client()
    if client:
        try:
            print("[INFO] Ingesting prospectus into ChromaDB knowledge base...")
            rag_app.invoke(rag_state)
            print("[INFO] Knowledge base initialized successfully.")
        except Exception as e:
            print(f"[WARNING] Could not initialize knowledge base embeddings: {e}")
    else:
        print("[INFO] OPENAI_API_KEY not configured. Set OPENAI_API_KEY in .env to enable RAG.")

# Initialize on module import
initialize_knowledge_base()

Queries = []

def admission_enquiry(query: str):
    result = res.invoke({"query": query})
    Queries.append(query)
    return result.get("answer", "No answer found.")
