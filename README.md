# RAG Companion Framework

Work in progress: a **multi-campaign** stack for TTRPG play in **SillyTavern**, backed by **Obsidian** vaults, **ChromaDB** for semantic memory, and a Python **ai-companion** service layer.

Current layout:

- `ai-companion/`: middleware components, validation runner, and service Docker build context
- `services/watcher/`: vault ingest + file watcher
- `rpg-companion/backend/campaigns/`: campaign configuration files (e.g. Senna, Starforged)

---

## What works today

**Infrastructure (Docker Compose)**

- **ChromaDB** on `127.0.0.1:8100` (host → container 8000), persistent volume.
- **Postgres** on `127.0.0.1:5432` and **Redis** on `127.0.0.1:6379`, both with persistent volumes.
- **Vault watcher** (`services/watcher`): watches configured vault paths, chunks markdown, embeds with Sentence Transformers, and upserts into per-campaign collections.
- **Compose profiles**:
  - `infra`: shared infra + watcher
  - `app`: middleware + SillyTavern instances (still in-progress)

**Watcher / indexing (local or container)**

- **`ingest.py`**: full re-index of a vault into a named collection (CLI; also available via `task ingest -- ...`).
- **`watcher.py`**: incremental updates on file changes; respects excluded folders (e.g. `Meta`, `.obsidian`, `Templates`) via env/config.

**AI companion package (`ai-companion`) — library + tests**

- **Shared data models** (`components/models.py`): exchanges, memories, clocks, state types used by upcoming pipeline code.
- **`ChromaClient`**: query/store helpers over a collection (distance filter, significance, milestones, batch upsert).
- **`OllamaClient`**: async HTTP to Ollama (`/api/generate`), JSON extraction with retry, heartbeat against `/api/tags`.
- **`MemoryExtractor`**: campaign-aware extraction logic with a memorability pre-filter, milestone phrase boosting (including `"solved"`), and structured logging on JSON parse failures.
- **`config.py`**: shared runtime config for Chroma, Ollama, OpenRouter, Postgres, and Redis (including DSN/URL helpers).
- **`validate.py`**: tiered test runner — **Tier 1** (pure logic/mocks), **Tier 2** (live Ollama), **Tier 3** (full stack). Run via `task test`, `task test:1`, `task test:3`, or `python ai-companion/validate.py --tier N`.

Compose declares a **`middleware` service** (port **8200**) from `ai-companion`, plus two SillyTavern app containers under the `app` profile.

---

## Not built yet (see [TODO](./docs/TODO.md))

Higher-level pipeline pieces (clock manager/assessor, state manager, OpenRouter client, injector, write-back, HTTP router) are **not** implemented end-to-end yet; the table in `docs/TODO.md` tracks status.

---

## Quick start

1. Copy and fill **`.env`** (`SENNA_VAULT_PATH`, `STARFORGED_VAULT_PATH`, plus keys/passwords).
2. Start core infra:
   - `task infra:up`
   - optional watcher: `docker compose --profile infra up watcher -d`
3. Install Python deps for local validation: `task install`
4. Run validation from repo root:
   - `task test:1` (fast, no live services)
   - `task test` (tier 2, requires Ollama)
5. Bring up app profile when needed: `docker compose --profile app up -d`

---

## Documentation

- [Changelog](./docs/CHANGELOG.md)
- [Work to do](./docs/TODO.md)
- [Architecture decisions](./docs/ArchitectureDecisions.md)
- [Validation tiers](./docs/Validation.md)
