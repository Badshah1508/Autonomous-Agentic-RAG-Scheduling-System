import os
import json
from threading import Lock
import numpy as np
import pandas as pd
from docx import Document
from PyPDF2 import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv

load_dotenv()

file_lock = Lock()


class LocalVectorStore:
    """Fast, 100% free, local vector store for prospectus retrieval."""
    def __init__(self):
        self.chunks = []
        self.vectorizer = TfidfVectorizer(stop_words='english')
        self.tfidf_matrix = None

    def add_documents(self, chunks):
        if not chunks:
            return
        self.chunks = chunks
        self.tfidf_matrix = self.vectorizer.fit_transform(chunks)
        print(f"[INFO] Indexed {len(chunks)} prospectus chunks in local vector store.")

    def similarity_search(self, query: str, top_k: int = 3):
        if not self.chunks or self.tfidf_matrix is None:
            return []
        try:
            query_vec = self.vectorizer.transform([query])
            scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
            top_indices = np.argsort(scores)[::-1][:top_k]
            matched = [self.chunks[i] for i in top_indices if scores[i] > 0.0]
            return matched if matched else self.chunks[:top_k]
        except Exception as e:
            print(f"[DEBUG] Local vector search error: {e}")
            return self.chunks[:top_k]


local_store = LocalVectorStore()


def get_llm_client():
    """
    Returns Groq client if GROQ_API_KEY is configured.
    Falls back to OpenAI client if OPENAI_API_KEY is available.
    """
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key and groq_key not in ("your_groq_api_key_here", "gsk_..."):
        try:
            from groq import Groq
            return Groq(api_key=groq_key), os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), "groq"
        except ImportError:
            print("[WARNING] groq package not installed. Run: pip install groq")

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key and openai_key not in ("your_openai_api_key_here", "API-KEY", "API_KEY"):
        try:
            from openai import OpenAI
            return OpenAI(api_key=openai_key), "gpt-4o", "openai"
        except ImportError:
            pass

    return None, None, None


# Step 1: Extract text from PDF
def extract_text_from_pdf(pdf_path):
    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
        return ""
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        print(f"[ERROR] Failed to extract text from PDF: {e}")
        return ""


# Step 2: Extract text from DOCX
def extract_text_from_docx(docx_path):
    if not os.path.exists(docx_path) or os.path.getsize(docx_path) == 0:
        return ""
    try:
        doc = Document(docx_path)
        text = ""
        for para in doc.paragraphs:
            if para.text:
                text += para.text + "\n"
        return text
    except Exception as e:
        print(f"[ERROR] Failed to extract text from DOCX: {e}")
        return ""


def chunk_text(text, chunk_size=1000):
    if not text:
        return []
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def store_embeddings_in_chromadb(chunks):
    """Indexes chunks in local vector store (instant, offline & free)."""
    if not chunks:
        print("[INFO] No text chunks to store.")
        return
    local_store.add_documents(chunks)


def generate_with_llm(prompt: str) -> str:
    """Generates response using Groq (Llama 3.3) or OpenAI."""
    client, model, provider = get_llm_client()
    if not client:
        return "⚠️ LLM API key missing. Please add your free GROQ_API_KEY to your .env file."

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error communicating with {provider} ({model}): {str(e)}"


# Alias for backward compatibility
generate_with_gpt = generate_with_llm


def rag_search(query: str) -> str:
    """Retrieves relevant prospectus chunks and queries Groq/Llama."""
    matched_chunks = local_store.similarity_search(query, top_k=3)
    if matched_chunks:
        context = "\n\n".join(matched_chunks)
    else:
        # Fallback: read prospectus directly
        base_dir = os.path.dirname(os.path.abspath(__file__))
        doc_path = os.path.join(base_dir, "Knowledge", "Prospectus.docx")
        context = extract_text_from_docx(doc_path) or "Sardar Vallabhbhai National Institute of Technology (SVNIT / NIT Surat)"

    client, model, provider = get_llm_client()
    if not client:
        return "⚠️ GROQ_API_KEY is not configured in .env. Please set GROQ_API_KEY to get AI answers."

    prompt = f"""
You are the helpful admission assistant for Sardar Vallabhbhai National Institute of Technology (SVNIT / NIT Surat).
Answer the user's questions clearly and accurately based on the college prospectus context below.
Provide specific details regarding eligibility, branches, fees, placements, and campus amenities whenever asked.
If a question is completely unrelated to college or education, politely invite them to ask about NIT Surat admissions.

Context:
{context}

Question: {query}

Answer:
"""
    return generate_with_llm(prompt)


def lead_gen(name: str, mob: int, lead_score: int):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    knowledge_dir = os.path.join(base_dir, "Knowledge")
    os.makedirs(knowledge_dir, exist_ok=True)
    csv_path = os.path.join(knowledge_dir, "Leads.csv")

    with file_lock:
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path)
            except Exception:
                df = pd.DataFrame(columns=["name", "mob", "lead_score"])
        else:
            df = pd.DataFrame(columns=["name", "mob", "lead_score"])

        df.loc[len(df)] = [name, mob, lead_score]
        df.to_csv(csv_path, index=False)
        print(f"[INFO] Saved lead to {csv_path}: {name}, {mob}, {lead_score}")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "Knowledge", "Prospectus.docx")

    _, extension = os.path.splitext(file_path)
    extension = extension.lower()

    text = ""
    if extension == '.pdf':
        text = extract_text_from_pdf(file_path)
    elif extension == '.docx':
        text = extract_text_from_docx(file_path)

    chunks = chunk_text(text, chunk_size=1000)
    print(f"Extracted {len(chunks)} chunks.")
    store_embeddings_in_chromadb(chunks)

    query = "What are the B.Tech programs offered at NIT Surat?"
    answer = rag_search(query)
    print("\nAnswer:\n", answer)
