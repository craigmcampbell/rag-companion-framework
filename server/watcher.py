"""
watcher.py — Watch the Obsidian vault and incrementally re-index changed files

Usage:
    python watcher.py --vault /path/to/your/vault

Dependencies:
    pip install watchdog chromadb sentence-transformers
"""

import argparse
import hashlib
import re
import time
from pathlib import Path

from sentence_transformers import SentenceTransformer
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from config import (
    COLLECTION, MODEL_NAME,
    CHUNK_SIZE, CHUNK_OVERLAP,
    get_chroma_client,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
    meta = {}
    match = re.match(r"^---\n(.*?)\n---\n(.*)", text, flags=re.DOTALL)
    if not match:
        return meta, text

    frontmatter_text, body = match.group(1), match.group(2)
    current_key = None
    list_items  = []

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
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"^- \[ \] (.+)$", r"(open) \1", text, flags=re.MULTILINE)
    text = re.sub(r"^- \[x\] (.+)$", r"(done) \1", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def stable_id(file_path: Path, chunk_index: int) -> str:
    return hashlib.md5(f"{file_path}::{chunk_index}".encode()).hexdigest()


def get_global_defaults(collection) -> dict:
    """Sample existing metadata keys so new chunks get empty defaults for all fields."""
    try:
        sample = collection.get(limit=500, include=["metadatas"])
        base_keys = {"source", "chunk", "note_title"}
        keys = set()
        for m in sample["metadatas"]:
            keys.update(k for k in m if k not in base_keys)
        return {k: "" for k in keys}
    except Exception:
        return {}


# ── Indexer ───────────────────────────────────────────────────────────────────

class VaultIndexer:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        print(f"Loading embedding model: {MODEL_NAME}")
        self.model      = SentenceTransformer(MODEL_NAME)
        self.client     = get_chroma_client()
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"Connected to collection ({self.collection.count()} chunks)")

    def index_file(self, path: Path):
        rel_path = str(path.relative_to(self.vault_path))
        try:
            raw         = path.read_text(encoding="utf-8", errors="ignore")
            frontmatter, _ = parse_frontmatter(raw)
            text        = clean_markdown(raw)

            if not text:
                print(f"  — {rel_path} (empty after clean, skipping)")
                return

            self._delete_chunks(rel_path)

            chunks     = chunk_text(text)
            note_title = path.stem
            merged     = {**get_global_defaults(self.collection), **frontmatter}

            ids           = [stable_id(path, i) for i in range(len(chunks))]
            metadatas     = [{"source": rel_path, "chunk": i, "note_title": note_title, **merged} for i in range(len(chunks))]
            titled_chunks = [f"Note: {note_title}\n\n{chunk}" for chunk in chunks]
            embeddings    = self.model.encode(titled_chunks, show_progress_bar=False).tolist()

            self.collection.upsert(
                ids=ids,
                documents=titled_chunks,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            print(f"  ✓ indexed {rel_path} ({len(chunks)} chunks)")

        except Exception as e:
            print(f"  ✗ failed to index {rel_path}: {e}")

    def _delete_chunks(self, rel_path: str):
        try:
            existing = self.collection.get(where={"source": rel_path}, include=[])
            if existing["ids"]:
                self.collection.delete(ids=existing["ids"])
                print(f"  🗑  removed {len(existing['ids'])} old chunks for {rel_path}")
        except Exception as e:
            print(f"  ✗ failed to delete chunks for {rel_path}: {e}")

    def delete_file(self, path: Path):
        self._delete_chunks(str(path.relative_to(self.vault_path)))


# ── Watchdog Handler ──────────────────────────────────────────────────────────

class VaultEventHandler(FileSystemEventHandler):
    def __init__(self, indexer: VaultIndexer):
        self.indexer = indexer
        self._recently_processed: dict[str, float] = {}
        self._debounce_seconds = 2.0

    def _is_relevant(self, event: FileSystemEvent) -> bool:
        path = Path(event.src_path)
        return path.suffix == ".md" and not any(p.startswith(".") for p in path.parts)

    def _debounce(self, src_path: str) -> bool:
        now = time.time()
        if now - self._recently_processed.get(src_path, 0) < self._debounce_seconds:
            return False
        self._recently_processed[src_path] = now
        return True

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory and self._is_relevant(event) and self._debounce(event.src_path):
            print(f"\n📝 Modified: {event.src_path}")
            self.indexer.index_file(Path(event.src_path))

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory and self._is_relevant(event) and self._debounce(event.src_path):
            print(f"\n✨ Created: {event.src_path}")
            self.indexer.index_file(Path(event.src_path))

    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory and self._is_relevant(event):
            print(f"\n🗑  Deleted: {event.src_path}")
            self.indexer.delete_file(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent):
        if event.is_directory:
            return
        src, dst = Path(event.src_path), Path(event.dest_path)
        if src.suffix == ".md" and not any(p.startswith(".") for p in src.parts):
            print(f"\n📦 Moved: {src} → {dst}")
            self.indexer.delete_file(src)
        if dst.suffix == ".md" and not any(p.startswith(".") for p in dst.parts):
            self.indexer.index_file(dst)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Watch Obsidian vault and auto re-index changes")
    parser.add_argument("--vault", required=True, help="Path to your Obsidian vault")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser().resolve()
    if not vault.exists():
        raise SystemExit(f"Vault not found: {vault}")

    indexer  = VaultIndexer(vault)
    handler  = VaultEventHandler(indexer)
    observer = Observer()
    observer.schedule(handler, str(vault), recursive=True)
    observer.start()

    print(f"\n👁  Watching {vault} for changes. Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\nWatcher stopped.")

    observer.join()