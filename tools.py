import os
import json
from threading import Lock
import pandas as pd
from docx import Document
from PyPDF2 import PdfReader
import chromadb
from chromadb import PersistentClient
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

file_lock = Lock()

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key in ("API-KEY", "API_KEY", "your_openai_api_key_here"):
        return None
    return OpenAI(api_key=api_key)

# Initialize ChromaDB client (persistent)
db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
os.makedirs(db_dir, exist_ok=True)
chroma_client = PersistentClient(path=db_dir)
collection = chroma_client.get_or_create_collection("my_collection")


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
    if not chunks:
        print("[INFO] No text chunks to store.")
        return

    client = get_openai_client()
    if not client:
        print("[WARNING] OPENAI_API_KEY is not set. Skipping embedding generation.")
        return

    try:
        for i, chunk in enumerate(chunks):
            emb = client.embeddings.create(
                model="text-embedding-3-small",
                input=chunk
            ).data[0].embedding

            collection.upsert(
                ids=[f"chunk_{i}"],
                documents=[chunk],
                embeddings=[emb]
            )

        print(f" Stored {len(chunks)} chunks in ChromaDB.")
    except Exception as e:
        print(f"[ERROR] Error storing embeddings in ChromaDB: {e}")


def generate_with_gpt(prompt):
    client = get_openai_client()
    if not client:
        return "OpenAI API key is missing. Please configure OPENAI_API_KEY in your .env file."

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Fallback to streaming if requested
        try:
            full_response = ""
            with client.responses.stream(
                model="gpt-4o",
                input=[{"role": "user", "content": prompt}]
            ) as stream:
                for event in stream:
                    if event.type == "response.output_text.delta":
                        full_response += event.delta
            return full_response
        except Exception:
            return f"Error communicating with OpenAI: {str(e)}"


def rag_search(query):
    client = get_openai_client()
    if not client:
        return "OpenAI API key is not configured. Please add OPENAI_API_KEY to your .env file."

    try:
        # Get embedding of query
        query_emb = client.embeddings.create(
            model="text-embedding-3-small",
            input=query
        ).data[0].embedding

        # Similar chunks
        results = collection.query(
            query_embeddings=[query_emb],
            n_results=3
        )

        docs = results.get("documents", [[]])
        if docs and len(docs[0]) > 0:
            context = "\n\n".join(docs[0])
        else:
            context = "No prospectus document chunks available."

        prompt = f"""
You are the helpful admission assistant for Sardar Vallabhbhai National Institute of Technology (SVNIT / NIT Surat).
You should politely answer queries related to the college, courses, admissions, eligibility, fees, facilities, and campus life using the context below.
If a question is completely unrelated to college admissions or NIT Surat, gently steer the user back to admission-related topics.

Context:
{context}

Question: {query}

Answer:
"""
        response = generate_with_gpt(prompt)
        return response
    except Exception as e:
        return f"Error retrieving admission information: {str(e)}"


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
    print("Answer:", answer)
