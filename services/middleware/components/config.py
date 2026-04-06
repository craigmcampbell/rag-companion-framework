"""
config.py — Shared configuration for ingest, watcher, and middleware.

All values can be overridden via environment variables or a .env file.
Campaigns are separated by collection name — adding a new campaign means
a new collection, a new vault mount, and a new ST instance. Nothing else.
"""

import os

# ── ChromaDB ──────────────────────────────────────────────────────────────────

CHROMA_HOST = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8100"))   # 81XX convention
CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_db") # fallback for local dev

# Collection name is a first-class config value.
# Each campaign gets its own collection.
# senna_memory | starforged_memory | ...
COLLECTION = os.environ.get("COLLECTION", "senna_memory")

# ── Embedding ─────────────────────────────────────────────────────────────────

# Model used for both ingest and query — must match across both.
# all-mpnet-base-v2 is a solid general-purpose choice.
# Upgrade path: BAAI/bge-large-en-v1.5 for better retrieval quality at
# the cost of slower embedding. Change here and re-ingest.
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-mpnet-base-v2")

# ── Chunking ──────────────────────────────────────────────────────────────────

CHUNK_SIZE    = int(os.environ.get("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "64"))

# ── Retrieval ─────────────────────────────────────────────────────────────────

# Default number of results to retrieve per query
TOP_K = int(os.environ.get("TOP_K", "5"))

# Maximum semantic distance to consider relevant (cosine, 0.0 = identical)
# Results beyond this threshold are filtered out even if TOP_K isn't filled
MAX_DISTANCE = float(os.environ.get("MAX_DISTANCE", "0.5"))

# ── Ollama (local inference for extraction/assessment) ────────────────────────

OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "localhost")
OLLAMA_PORT  = int(os.environ.get("OLLAMA_PORT", "11434"))
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral")

# ── OpenRouter (DeepSeek for primary RP) ──────────────────────────────────────

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat")

# ── Middleware ────────────────────────────────────────────────────────────────

MIDDLEWARE_HOST = os.environ.get("MIDDLEWARE_HOST", "localhost")
MIDDLEWARE_PORT = int(os.environ.get("MIDDLEWARE_PORT", "8200"))

# ── Obsidian / Write-back ─────────────────────────────────────────────────────

VAULT_PATH   = os.environ.get("VAULT_PATH", "")
SESSIONS_DIR = os.environ.get("SESSIONS_DIR", "Sessions")  # relative to vault root
META_DIR     = os.environ.get("META_DIR", "Meta")          # excluded from indexing


# ── Clients ───────────────────────────────────────────────────────────────────

def get_chroma_client():
    """
    Return the appropriate ChromaDB client based on environment config.
    HTTP client is used when CHROMA_HOST is set (production/Docker).
    PersistentClient is the local dev fallback.
    """
    import chromadb
    if CHROMA_HOST and CHROMA_HOST != "localhost":
        return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    else:
        # localhost — use HttpClient if ChromaDB server is running,
        # PersistentClient if running embedded for local dev
        try:
            client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            client.heartbeat()  # verify connection
            return client
        except Exception:
            print(f"ChromaDB HTTP unavailable at {CHROMA_HOST}:{CHROMA_PORT}, "
                  f"falling back to PersistentClient at {CHROMA_PATH}")
            return chromadb.PersistentClient(path=CHROMA_PATH)


def get_embedding_function():
    """
    Return the shared embedding function.

    Using ChromaDB's built-in SentenceTransformerEmbeddingFunction means
    embeddings are handled automatically on both upsert and query —
    no manual model.encode() calls needed anywhere.

    Both ingest.py and the middleware client must use this function
    so query embeddings match stored embeddings.
    """
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    return SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)