"""
server.py — FastAPI RAG server for Obsidian vault

Usage:
    uvicorn server:app --host 127.0.0.1 --port 8000 --reload

Dependencies:
    pip install fastapi uvicorn chromadb sentence-transformers anthropic
"""

import json
import os
import re
import anthropic

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

from config import (
    COLLECTION, MODEL_NAME,
    CLAUDE_MODEL, TOP_K, MAX_TOKENS,
    get_chroma_client,
)

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a helpful assistant with access to the user's personal Obsidian notes.
Answer questions using the provided context from their notes.
If the context doesn't contain enough information to answer, say so clearly — do not make things up.
When relevant, mention which note(s) the information came from."""

FILTER_EXTRACTION_PROMPT = """You help extract structured metadata filters from natural language queries about an Obsidian note vault.

Notes may have frontmatter properties stored as metadata. Common ones include:
- book-status: e.g. "Finished", "Reading", "Abandoned" (capitalize first letter)
- years-read: comma-separated years e.g. "2024,2025"
- type: e.g. "book", "article"
- Any other frontmatter key the user references

Given a query, return a JSON object with:
- "where": a ChromaDB $and/$or filter object, or null if no structured filter applies
- "search_query": a cleaned version of the query for vector search (remove filter-specific parts)

ChromaDB filter operators: $eq, $ne, $contains, $and, $or

Examples:
Query: "what books did I finish in 2025?"
{"where": {"$and": [{"book-status": {"$eq": "Finished"}}, {"years-read": {"$contains": "2025"}}]}, "search_query": "books"}

Query: "books I'm currently reading"
{"where": {"book-status": {"$eq": "Reading"}}, "search_query": "books currently reading"}

Query: "what did I learn about Python recursion?"
{"where": null, "search_query": "Python recursion"}

Return ONLY a valid JSON object on a single line. No explanation, no markdown, no code fences."""

# ── Startup ───────────────────────────────────────────────────────────────────
# Load variables from a project-local `.env` file.
# This lets you run `uvicorn server:app ...` without manually exporting keys.
_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(_BASE_DIR / ".env")

app = FastAPI(title="Obsidian RAG Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["app://obsidian.md", "http://localhost", "http://127.0.0.1"],
    allow_methods=["*"],
    allow_headers=["*"],
)

print(f"Loading embedding model: {MODEL_NAME}")
embedder = SentenceTransformer(MODEL_NAME)

chroma_client = get_chroma_client()
collection = chroma_client.get_or_create_collection(
    name=COLLECTION,
    metadata={"hnsw:space": "cosine"},
)

claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

print(f"Server ready. Collection has {collection.count()} chunks indexed.")

# ── Schema ────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    top_k: int = TOP_K

class SourceChunk(BaseModel):
    source: str
    chunk: int
    text: str
    distance: float

class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]

# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_filters(query: str) -> tuple[dict | None, str]:
    """
    Ask Claude to extract structured metadata filters from the query.
    Returns (where_filter, cleaned_search_query).
    Falls back to (None, original_query) on any error.
    """
    try:
        response = claude.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            system=FILTER_EXTRACTION_PROMPT,
            messages=[{"role": "user", "content": query}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
        if not raw:
            print("Filter extraction returned empty response, using plain query")
            return None, query
        parsed = json.loads(raw)
        where  = parsed.get("where") or None
        search = parsed.get("search_query") or query
        print(f"Filter extracted — where: {where} | search: {search!r}")
        return where, search
    except Exception as e:
        print(f"Filter extraction failed, using plain query: {e}")
        return None, query

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "chunks_indexed": collection.count(),
        "model": CLAUDE_MODEL,
        "embedding_model": MODEL_NAME,
        "top_k": TOP_K,
    }


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # 1. Extract metadata filters + cleaned search query
    where_filter, search_query = extract_filters(req.query)

    # 2. Embed the cleaned search query
    query_embedding = embedder.encode(search_query).tolist()

    # 3. Retrieve top-k chunks, applying metadata filter if present
    query_kwargs = dict(
        query_embeddings=[query_embedding],
        n_results=req.top_k,
        include=["documents", "metadatas", "distances"],
    )
    if where_filter:
        query_kwargs["where"] = where_filter

    try:
        results = collection.query(**query_kwargs)
    except Exception as e:
        print(f"Filtered query failed ({e}), retrying without filter")
        query_kwargs.pop("where", None)
        results = collection.query(**query_kwargs)

    docs      = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    print(f"Query returned {len(docs)} chunks (filtered: {where_filter is not None})")

    if not docs:
        raise HTTPException(status_code=404, detail="No relevant notes found")

    # 4. Build context block for Claude
    context_parts = []
    for i, (doc, meta) in enumerate(zip(docs, metadatas)):
        context_parts.append(f"[{i+1}] From '{meta['source']}':\n{doc}")
    context = "\n\n---\n\n".join(context_parts)

    user_message = f"""Context from my notes:

{context}

---

Question: {req.query}"""

    # 5. Call Claude
    response = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    answer = response.content[0].text

    # 6. Return answer + sources
    sources = [
        SourceChunk(
            source=meta["source"],
            chunk=meta["chunk"],
            text=doc,
            distance=round(dist, 4),
        )
        for doc, meta, dist in zip(docs, metadatas, distances)
    ]

    return QueryResponse(answer=answer, sources=sources)