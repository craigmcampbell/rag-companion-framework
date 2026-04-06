"""
config.py — Configuration for the watcher and ingest services.

All values can be overridden via environment variables or a .env file.
This config is intentionally scoped to what the watcher/ingest services
need — it does not duplicate middleware concerns.
"""

import os

# ── ChromaDB ──────────────────────────────────────────────────────────────────

CHROMA_HOST = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8100"))
CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_db")  # local dev fallback

# Default collection — overridden per-vault in watcher_config.yml
# and via --collection arg in ingest.py
COLLECTION = os.environ.get("COLLECTION", "senna_memory")

# ── Embedding ─────────────────────────────────────────────────────────────────

# Must match the middleware's EMBEDDING_MODEL exactly.
# If you change this, re-ingest all vaults.
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-mpnet-base-v2")

# ── Chunking ──────────────────────────────────────────────────────────────────

CHUNK_SIZE    = int(os.environ.get("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "64"))

# ── Vault exclusions ──────────────────────────────────────────────────────────

# Folders to skip during indexing (relative folder names, not full paths).
# Meta contains operational docs that should never appear in RAG retrieval.
EXCLUDED_FOLDERS = os.environ.get(
    "EXCLUDED_FOLDERS", "Meta,.obsidian,Templates"
).split(",")


# ── Clients ───────────────────────────────────────────────────────────────────

def get_chroma_client():
    """
    Return the appropriate ChromaDB client.
    Tries HTTP first (production/Docker), falls back to PersistentClient for local dev.
    """
    import chromadb
    try:
        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        client.heartbeat()
        return client
    except Exception:
        print(
            f"ChromaDB HTTP unavailable at {CHROMA_HOST}:{CHROMA_PORT}, "
            f"falling back to PersistentClient at {CHROMA_PATH}"
        )
        return chromadb.PersistentClient(path=CHROMA_PATH)


def get_embedding_function():
    """
    Return the shared ChromaDB embedding function.

    Using SentenceTransformerEmbeddingFunction means ChromaDB handles
    embedding automatically on both upsert and query — no manual
    model.encode() calls needed anywhere.

    Both ingest.py and watcher.py must use this function so embeddings
    stay consistent. The middleware uses the same model via its own config.
    """
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    return SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
