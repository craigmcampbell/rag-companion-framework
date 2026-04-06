"""
ingest.py — Full re-index of an Obsidian vault into ChromaDB.

Use this for initial indexing or when you need a clean re-index.
For incremental updates on file changes, use watcher.py instead.

Usage:
    python ingest.py --vault /path/to/vault
    python ingest.py --vault /path/to/vault --collection starforged_memory
    python ingest.py --vault /path/to/vault --reset    # wipe + re-index

Dependencies:
    pip install chromadb sentence-transformers python-dotenv
"""

import argparse
import hashlib
import re
from pathlib import Path

from dotenv import load_dotenv

from config import (
    COLLECTION,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    EXCLUDED_FOLDERS,
    get_chroma_client,
    get_embedding_function,
)

load_dotenv()

# ── Helpers ───────────────────────────────────────────────────────────────────

def iter_markdown_files(vault_path: Path, excluded: list[str]) -> list[Path]:
    """
    Yield all .md files under vault_path, skipping:
    - Hidden directories (prefixed with .)
    - Any folder in the excluded list (Meta, Templates, etc.)
    """
    files = []
    for path in vault_path.rglob("*.md"):
        parts = path.relative_to(vault_path).parts
        if any(part.startswith(".") for part in parts):
            continue
        if any(part in excluded for part in parts):
            continue
        files.append(path)
    return files


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """
    Extract YAML frontmatter and return (metadata_dict, body).
    List values stored as comma-separated strings for ChromaDB compatibility.
    """
    meta: dict = {}
    match = re.match(r"^---\n(.*?)\n---\n(.*)", text, flags=re.DOTALL)
    if not match:
        return meta, text

    frontmatter_text, body = match.group(1), match.group(2)
    current_key = None
    list_items: list[str] = []

    for line in frontmatter_text.splitlines():
        kv = re.match(r"^([\w-]+):\s*(.+)$", line)
        if kv:
            if current_key and list_items:
                meta[current_key] = ",".join(list_items)
                list_items = []
            current_key = kv.group(1)
            value = kv.group(2).strip().strip('"').strip("'")
            if value.startswith("[") and value.endswith("]"):
                items = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",")]
                meta[current_key] = ",".join(i for i in items if i)
                current_key = None
            else:
                meta[current_key] = value
            continue

        key_only = re.match(r"^([\w-]+):\s*$", line)
        if key_only:
            if current_key and list_items:
                meta[current_key] = ",".join(list_items)
                list_items = []
            current_key = key_only.group(1)
            list_items = []
            continue

        item = re.match(r"^\s+-\s+(.+)$", line)
        if item and current_key:
            list_items.append(item.group(1).strip().strip('"').strip("'"))
            continue

    if current_key and list_items:
        meta[current_key] = ",".join(list_items)

    return meta, body


def clean_markdown(text: str) -> str:
    """Strip frontmatter and reduce noise while keeping readable content."""
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"^- \[ \] (.+)$", r"(open) \1", text, flags=re.MULTILINE)
    text = re.sub(r"^- \[x\] (.+)$", r"(done) \1", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str) -> list[str]:
    """Split text into overlapping character-level chunks."""
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def stable_id(file_path: Path, chunk_index: int) -> str:
    """Deterministic chunk ID so re-runs upsert cleanly without duplicates."""
    return hashlib.md5(f"{file_path}::{chunk_index}".encode()).hexdigest()


# ── Main ──────────────────────────────────────────────────────────────────────

def ingest(vault_path: Path, collection_name: str, reset: bool = False) -> None:
    print(f"Loading embedding function ({collection_name})...")
    embedding_fn = get_embedding_function()

    client = get_chroma_client()

    if reset:
        print(f"Resetting collection '{collection_name}'...")
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    excluded = EXCLUDED_FOLDERS
    md_files = iter_markdown_files(vault_path, excluded)
    print(f"Found {len(md_files)} markdown files in {vault_path}")
    if excluded:
        print(f"Excluding folders: {', '.join(excluded)}")

    # First pass: collect every frontmatter key across the vault.
    # ChromaDB requires all chunks to have the same metadata keys —
    # missing keys cause filter failures, so we default-fill with "".
    print("Scanning frontmatter keys across vault...")
    all_frontmatter_keys: set[str] = set()
    file_frontmatters: dict[Path, dict] = {}

    for md_file in md_files:
        try:
            raw = md_file.read_text(encoding="utf-8", errors="ignore")
            fm, _ = parse_frontmatter(raw)
            all_frontmatter_keys.update(fm.keys())
            file_frontmatters[md_file] = fm
        except Exception:
            file_frontmatters[md_file] = {}

    global_defaults = {key: "" for key in all_frontmatter_keys}
    print(f"Discovered {len(global_defaults)} unique frontmatter keys across vault")

    total_chunks = 0
    failed: list[tuple[str, str]] = []

    for md_file in md_files:
        rel_path = str(md_file.relative_to(vault_path))
        try:
            raw = md_file.read_text(encoding="utf-8", errors="ignore")
            frontmatter = file_frontmatters.get(md_file, {})
            text = clean_markdown(raw)

            if not text:
                print(f"  — {rel_path} (empty after clean, skipping)")
                continue

            chunks = chunk_text(text)
            note_title = md_file.stem
            merged = {**global_defaults, **frontmatter}

            ids = [stable_id(md_file, i) for i in range(len(chunks))]
            titled_chunks = [f"Note: {note_title}\n\n{chunk}" for chunk in chunks]
            metadatas = [
                {"source": rel_path, "chunk": str(i), "note_title": note_title, **merged}
                for i in range(len(chunks))
            ]

            # Embedding is handled automatically by the embedding_function
            # attached to the collection — no manual model.encode() needed.
            collection.upsert(
                ids=ids,
                documents=titled_chunks,
                metadatas=metadatas,
            )

            total_chunks += len(chunks)
            print(f"  ✓ {rel_path} ({len(chunks)} chunks)")

        except Exception as e:
            print(f"  ✗ {rel_path} — ERROR: {e}")
            failed.append((rel_path, str(e)))

    print(f"\nDone. {total_chunks} chunks from {len(md_files) - len(failed)} files indexed.")
    print(f"Collection '{collection_name}' now contains {collection.count()} total chunks.")

    if failed:
        print(f"\n{len(failed)} file(s) failed:")
        for path, err in failed:
            print(f"  ✗ {path}: {err}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Full re-index of an Obsidian vault into ChromaDB"
    )
    parser.add_argument("--vault", required=True, help="Path to your Obsidian vault")
    parser.add_argument(
        "--collection",
        default=COLLECTION,
        help=f"ChromaDB collection name (default: {COLLECTION})",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe the collection before indexing",
    )
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.exists():
        raise SystemExit(f"Vault not found: {vault}")

    ingest(vault, collection_name=args.collection, reset=args.reset)
