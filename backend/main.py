import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from openai import OpenAI

import pypdf as PyPDF2
import re

# --- Settings ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", None)
PDF_PATH = os.getenv("DOWNLOAD_PDF", "./lecture.pdf")

# --- OpenAI ---
api_key = OPENAI_API_KEY
client = OpenAI(api_key=api_key)


# --- Chunking PDF ---
def extract_pdf_chunks(pdf_path, chunk_size=500, overlap=100):
    """Extracts text from PDF and splits into overlapping chunks."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at {pdf_path}")
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        full_text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                full_text += page_text + "\n"
    # Clean excessive whitespace
    full_text = re.sub(r"\s+", " ", full_text)
    # Split into chunks
    chunks = []
    start = 0
    while start < len(full_text):
        end = start + chunk_size
        chunk = full_text[start:end]
        chunks.append(chunk)
        start += chunk_size - overlap
    return chunks

# On startup, extract chunks
try:
    PDF_CHUNKS = extract_pdf_chunks(PDF_PATH)
except Exception as exc:
    PDF_CHUNKS = []
    print(f"Warning: Failed to load PDF chunks: {exc}")

# --- DB (history) ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./faq.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class QAHistory(Base):
    __tablename__ = "qa_history"
    id = Column(Integer, primary_key=True, index=True)
    question = Column(String)
    answer = Column(String)

Base.metadata.create_all(bind=engine)

# --- FastAPI ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Schemas ---
class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    answer: str

class QAPair(BaseModel):
    question: str
    answer: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Retrieval from Chunks ---
def find_relevant_chunks(question, chunks, top_k=3):
    """Very basic retrieval: rank by shared words with the question."""
    question_words = set(re.findall(r'\w+', question.lower()))
    chunk_scores = []
    for chunk in chunks:
        chunk_words = set(re.findall(r'\w+', chunk.lower()))
        score = len(chunk_words & question_words)
        chunk_scores.append((score, chunk))
    # Take top_k nonzero-scored chunks, or just top ones
    sorted_chunks = [c for s, c in sorted(chunk_scores, reverse=True) if s > 0]
    if not sorted_chunks:
        sorted_chunks = [c for _, c in sorted(chunk_scores, reverse=True)]
    return sorted_chunks[:top_k]

def generate_answer_with_openai(user_question: str, context: str) -> str:
    prompt = (
        "You are a helpful assistant for information in docs. "
        "Answer ONLY using the provided rules context. "
        "If the answer is not found, say honestly you don't know. "
        f"\nRules Context:\n{context}\n"
        f"User Question: {user_question}\n"
        "Answer:"
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=256,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return "AI error: " + str(exc)

@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest, db: Session = Depends(get_db)):
    if not PDF_CHUNKS:
        return AskResponse(answer="PDF is not loaded or missing.")
    context_chunks = find_relevant_chunks(request.question, PDF_CHUNKS)
    context = "\n---\n".join(context_chunks)
    answer = generate_answer_with_openai(request.question, context)
    # Store in history
    db.add(QAHistory(question=request.question, answer=answer))
    db.commit()
    return AskResponse(answer=answer)

@app.get("/api/history", response_model=List[QAPair])
def get_history(db: Session = Depends(get_db)):
    return [
        QAPair(question=e.question, answer=e.answer)
        for e in db.query(QAHistory).order_by(QAHistory.id.desc()).all()
    ]
