"""
config.py — Shared configuration for ingest, server, and watcher.
All values can be overridden via environment variables or a .env file.
"""

import os

# ── ChromaDB ──────────────────────────────────────────────────────────────────

CHROMA_HOST = os.environ.get("CHROMA_HOST", "")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_db")
COLLECTION  = os.environ.get("COLLECTION", "obsidian_vault")

# ── Embedding model ───────────────────────────────────────────────────────────

MODEL_NAME = os.environ.get("MODEL_NAME", "all-mpnet-base-v2")

# ── Chunking ──────────────────────────────────────────────────────────────────

CHUNK_SIZE    = int(os.environ.get("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "64"))

# ── Server ────────────────────────────────────────────────────────────────────

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
TOP_K        = int(os.environ.get("TOP_K", "5"))
MAX_TOKENS   = int(os.environ.get("MAX_TOKENS", "1024"))


def get_chroma_client():
    """Return the appropriate ChromaDB client based on environment config."""
    import chromadb
    if CHROMA_HOST:
        print(f"Connecting to ChromaDB at {CHROMA_HOST}:{CHROMA_PORT}")
        return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    else:
        print(f"Using local ChromaDB at {CHROMA_PATH}")
        return chromadb.PersistentClient(path=CHROMA_PATH)