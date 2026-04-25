"""
config.py — Shared configuration for the ai-companion middleware.

All values can be overridden via environment variables or a .env file.
Campaigns are separated by collection name — adding a new campaign means
a new collection, a new vault mount, and a new ST instance. Nothing else.
"""

import os
from urllib.parse import quote_plus

# ── ChromaDB ──────────────────────────────────────────────────────────────────

CHROMA_HOST = os.environ.get("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8100"))
CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_db")

COLLECTION = os.environ.get("COLLECTION", "senna_memory")

# ── Embedding ─────────────────────────────────────────────────────────────────

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-mpnet-base-v2")

# ── Chunking ──────────────────────────────────────────────────────────────────

CHUNK_SIZE    = int(os.environ.get("CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "64"))

# ── Retrieval ─────────────────────────────────────────────────────────────────

TOP_K        = int(os.environ.get("TOP_K", "5"))
MAX_DISTANCE = float(os.environ.get("MAX_DISTANCE", "0.5"))

# ── Ollama ────────────────────────────────────────────────────────────────────

OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "localhost")
OLLAMA_PORT  = int(os.environ.get("OLLAMA_PORT", "11434"))
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "mistral-nemo:12b")

# ── OpenRouter ────────────────────────────────────────────────────────────────

OPENROUTER_API_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL    = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat")

# ── Middleware ────────────────────────────────────────────────────────────────

MIDDLEWARE_HOST = os.environ.get("MIDDLEWARE_HOST", "localhost")
MIDDLEWARE_PORT = int(os.environ.get("MIDDLEWARE_PORT", "8200"))

# ── Postgres ──────────────────────────────────────────────────────────────────

POSTGRES_HOST     = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT     = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_USER     = os.environ.get("POSTGRES_USER", "rpg")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "rpg_local_only")
POSTGRES_DB       = os.environ.get("POSTGRES_DB", "rpg_companion")

def get_postgres_dsn() -> str:
    """Return a SQLAlchemy-compatible DSN for Postgres."""
    user = quote_plus(POSTGRES_USER)
    password = quote_plus(POSTGRES_PASSWORD)
    return (
        f"postgresql+asyncpg://{user}:{password}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

def get_postgres_dsn_sync() -> str:
    """Return a synchronous DSN for Alembic migrations."""
    user = quote_plus(POSTGRES_USER)
    password = quote_plus(POSTGRES_PASSWORD)
    return (
        f"postgresql+psycopg2://{user}:{password}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

# ── Redis ─────────────────────────────────────────────────────────────────────

REDIS_HOST     = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT     = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "redis_local_only")
REDIS_DB       = int(os.environ.get("REDIS_DB", "0"))

def get_redis_url() -> str:
    """Return a redis:// URL for use with redis-py or aioredis."""
    password = quote_plus(REDIS_PASSWORD)
    return f"redis://:{password}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# ── Obsidian / Write-back ─────────────────────────────────────────────────────

VAULT_PATH   = os.environ.get("VAULT_PATH", "")
SESSIONS_DIR = os.environ.get("SESSIONS_DIR", "Sessions")
META_DIR     = os.environ.get("META_DIR", "Meta")


# ── Clients ───────────────────────────────────────────────────────────────────

def get_chroma_client():
    """Return the appropriate ChromaDB client based on environment config."""
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
    """Return the shared ChromaDB embedding function."""
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    return SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)