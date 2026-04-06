"""
watcher.py — Watch one or more Obsidian vaults and incrementally re-index changes.

Reads vault/collection pairs from watcher_config.yml. Adding a new campaign
is just a new entry in that file — no code changes needed.

Usage:
    python watcher.py                                    # uses watcher_config.yml
    python watcher.py --config /path/to/config.yml      # explicit config path

watcher_config.yml format:
    vaults:
      - path: /vaults/senna
        collection: senna_memory
      - path: /vaults/starforged
        collection: starforged_memory

Dependencies:
    pip install chromadb sentence-transformers watchdog pyyaml python-dotenv
"""

import argparse
import hashlib
import re
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    EXCLUDED_FOLDERS,
    get_chroma_client,
    get_embedding_function,
)

load_dotenv()

DEFAULT_CONFIG = Path(__file__).parent / "watcher_config.yml"

# ── Helpers (shared with ingest.py) ──────────────────────────────────────────

def parse_frontmatter(text: str) -> tuple[dict, str]:
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
        chunks.append(text[start : start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def stable_id(file_path: Path, chunk_index: int) -> str:
    return hashlib.md5(f"{file_path}::{chunk_index}".encode()).hexdigest()


def is_excluded(path: Path, vault_path: Path, excluded: list[str]) -> bool:
    """Return True if any part of the path relative to vault is in the excluded list."""
    try:
        parts = path.relative_to(vault_path).parts
    except ValueError:
        return False
    return any(part in excluded for part in parts) or any(
        part.startswith(".") for part in parts
    )


# ── Indexer ───────────────────────────────────────────────────────────────────

class VaultIndexer:
    """
    Handles indexing for a single vault/collection pair.
    One VaultIndexer is created per vault entry in watcher_config.yml.
    """

    def __init__(self, vault_path: Path, collection_name: str, embedding_fn):
        self.vault_path = vault_path
        self.collection_name = collection_name
        self._excluded = EXCLUDED_FOLDERS

        chroma = get_chroma_client()
        self.collection = chroma.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )
        print(
            f"  [{collection_name}] Connected — "
            f"{self.collection.count()} chunks indexed from {vault_path}"
        )

    def _get_global_defaults(self) -> dict:
        """
        Sample existing metadata keys so new chunks get empty defaults
        for all fields (ChromaDB filter requirement).
        """
        try:
            sample = self.collection.get(limit=500, include=["metadatas"])
            base_keys = {"source", "chunk", "note_title"}
            keys: set[str] = set()
            for m in sample["metadatas"]:
                keys.update(k for k in m if k not in base_keys)
            return {k: "" for k in keys}
        except Exception:
            return {}

    def index_file(self, path: Path) -> None:
        if is_excluded(path, self.vault_path, self._excluded):
            return

        rel_path = str(path.relative_to(self.vault_path))
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
            frontmatter, _ = parse_frontmatter(raw)
            text = clean_markdown(raw)

            if not text:
                print(f"  [{self.collection_name}] — {rel_path} (empty, skipping)")
                return

            self._delete_chunks(rel_path)

            chunks = chunk_text(text)
            note_title = path.stem
            merged = {**self._get_global_defaults(), **frontmatter}

            ids = [stable_id(path, i) for i in range(len(chunks))]
            titled_chunks = [f"Note: {note_title}\n\n{chunk}" for chunk in chunks]
            metadatas = [
                {"source": rel_path, "chunk": str(i), "note_title": note_title, **merged}
                for i in range(len(chunks))
            ]

            # Embedding handled automatically by the collection's embedding_function
            self.collection.upsert(
                ids=ids,
                documents=titled_chunks,
                metadatas=metadatas,
            )
            print(f"  [{self.collection_name}] ✓ {rel_path} ({len(chunks)} chunks)")

        except Exception as e:
            print(f"  [{self.collection_name}] ✗ {rel_path}: {e}")

    def delete_file(self, path: Path) -> None:
        if is_excluded(path, self.vault_path, self._excluded):
            return
        self._delete_chunks(str(path.relative_to(self.vault_path)))

    def _delete_chunks(self, rel_path: str) -> None:
        try:
            existing = self.collection.get(where={"source": rel_path}, include=[])
            if existing["ids"]:
                self.collection.delete(ids=existing["ids"])
                print(
                    f"  [{self.collection_name}] 🗑  removed "
                    f"{len(existing['ids'])} old chunks for {rel_path}"
                )
        except Exception as e:
            print(f"  [{self.collection_name}] ✗ failed to delete chunks for {rel_path}: {e}")


# ── Watchdog Handler ──────────────────────────────────────────────────────────

class VaultEventHandler(FileSystemEventHandler):
    def __init__(self, indexer: VaultIndexer):
        self.indexer = indexer
        self._recently_processed: dict[str, float] = {}
        self._debounce_seconds = 2.0

    def _is_relevant(self, event: FileSystemEvent) -> bool:
        path = Path(event.src_path)
        return path.suffix == ".md" and not is_excluded(
            path, self.indexer.vault_path, EXCLUDED_FOLDERS
        )

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
        src = Path(event.src_path)
        dst = Path(getattr(event, "dest_path", ""))
        if src.suffix == ".md" and not is_excluded(src, self.indexer.vault_path, EXCLUDED_FOLDERS):
            print(f"\n📦 Moved: {src} → {dst}")
            self.indexer.delete_file(src)
        if dst.suffix == ".md" and not is_excluded(dst, self.indexer.vault_path, EXCLUDED_FOLDERS):
            self.indexer.index_file(dst)


# ── Config loading ────────────────────────────────────────────────────────────

def load_vault_config(config_path: Path) -> list[dict]:
    """
    Load vault/collection pairs from watcher_config.yml.

    Expected format:
        vaults:
          - path: /vaults/senna
            collection: senna_memory
          - path: /vaults/starforged
            collection: starforged_memory
    """
    if not config_path.exists():
        raise SystemExit(f"Watcher config not found: {config_path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    vaults = data.get("vaults", [])
    if not vaults:
        raise SystemExit(f"No vaults defined in {config_path}")

    validated = []
    for entry in vaults:
        path = Path(entry.get("path", "")).expanduser().resolve()
        collection = entry.get("collection", "").strip()
        if not path.exists():
            print(f"  ⚠️  Vault not found, skipping: {path}")
            continue
        if not collection:
            print(f"  ⚠️  No collection name for {path}, skipping")
            continue
        validated.append({"path": path, "collection": collection})

    if not validated:
        raise SystemExit("No valid vaults to watch.")

    return validated


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Watch Obsidian vaults and auto re-index changes into ChromaDB"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Path to watcher config YAML (default: {DEFAULT_CONFIG})",
    )
    args = parser.parse_args()

    vault_configs = load_vault_config(args.config)

    # Load the embedding function once — shared across all vaults
    print("Loading embedding function...")
    embedding_fn = get_embedding_function()

    observer = Observer()

    print(f"\nStarting watchers for {len(vault_configs)} vault(s):\n")
    for vc in vault_configs:
        indexer = VaultIndexer(
            vault_path=vc["path"],
            collection_name=vc["collection"],
            embedding_fn=embedding_fn,
        )
        handler = VaultEventHandler(indexer)
        observer.schedule(handler, str(vc["path"]), recursive=True)
        print(f"  👁  {vc['path']} → {vc['collection']}")

    observer.start()
    print("\nWatching for changes. Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\nWatcher stopped.")

    observer.join()
