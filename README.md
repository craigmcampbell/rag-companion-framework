# RAG Companion Framework

Work in progress: a **multi-campaign** stack for TTRPG play in **SillyTavern**, backed by **Obsidian** vaults, **ChromaDB** for semantic memory, and Python **middleware** (inference and retrieval) that is still being layered in.

Design intent is **one shared Chroma + middleware**, with **separate ST instances and vaults** per campaign (e.g. Senna vs Starforged). See [Architecture decisions](./docs/ArchitectureDecisions.md).

---

## What works today

**Infrastructure (Docker Compose)**

- **ChromaDB** on `127.0.0.1:8100` (host → container 8000), persistent volume.
- **Vault watcher** (`services/watcher`): watches configured vault paths, chunks markdown, embeds with Sentence Transformers, upserts into **per-campaign collections**. Config comes from `services/watcher/watcher_config.yml` (vault path + `collection` pairs). Compose mounts two vault roots (`SENNA_VAULT_PATH`, `STARFORGED_VAULT_PATH`) read-only under `/vaults/...`.
- **SillyTavern** — two containers: **Senna** on `127.0.0.1:8010`, **Starforged** on `127.0.0.1:8011`, with separate config/data dirs under `sillytavern/`.

**Watcher / indexing (local or container)**

- **`ingest.py`**: full re-index of a vault into a named collection (CLI; also available via `task ingest -- ...`).
- **`watcher.py`**: incremental updates on file changes; respects excluded folders (e.g. `Meta`, `.obsidian`, `Templates`) via env/config.

**Middleware package (`services/middleware`) — library + tests**

- **Shared data models** (`components/models.py`): exchanges, memories, clocks, state types used by upcoming pipeline code.
- **`ChromaClient`**: query/store helpers over a collection (distance filter, significance, milestones, batch upsert).
- **`OllamaClient`**: async HTTP to Ollama (`/api/generate`), JSON extraction with retry, heartbeat against `/api/tags`.
- **`validate.py`**: tiered test runner — **Tier 1** (models, Chroma client mocks, Ollama client mocks), **Tier 2** (live Ollama), **Tier 3** reserved for full stack. Run via `task test`, `task test:2`, or `python services/middleware/validate.py`.

Compose also declares a **`middleware` service** (port **8200**, env for Chroma, Ollama, OpenRouter). The repo currently holds **components and tests** under `services/middleware`, not a finished long-running HTTP app; add a Dockerfile + entrypoint here when the router/API exists.

---

## Not built yet (see [TODO](./docs/TODO.md))

Higher-level pipeline pieces (memory extractor, clock manager/assessor, state manager, OpenRouter client, injector, write-back, HTTP router) are **not** implemented end-to-end yet; the table in `docs/TODO.md` tracks status.

---

## Quick start

1. Copy and fill **`.env`** (vault paths, API keys as needed). Compose expects at least `SENNA_VAULT_PATH` and `STARFORGED_VAULT_PATH` for watcher mounts.
2. **`docker compose up -d`** — Chroma, watcher, ST instances; bring up **`middleware`** when its image and app entrypoint exist.
3. **Python deps** (local dev / tests): `task install` or `pip install -r requirements.txt`, then `task test` from the repo root.

---

## Documentation

- [Changelog](./docs/CHANGELOG.md)
- [Work to do](./docs/TODO.md)
- [Architecture decisions](./docs/ArchitectureDecisions.md)
- [Validation tiers](./docs/Validation.md)
