# Changelog

## 2026-04-05

### Added

- `services/middleware` Docker image and Compose service (port 8200) with Ollama/OpenRouter-oriented env defaults
- Async `OllamaClient` for local `/api/generate` (JSON parsing, retries, heartbeat) plus tier 1–2 tests wired into `validate.py`
- Root `requirements.txt` (httpx, PyYAML, etc.) and `pyrightconfig.json` for a standard venv and editor type resolution
- Taskfile tasks: `install`, `activate`, and `test:*` aimed at `services/middleware`

### Changed

- Middleware and vault watcher code organized under `services/middleware` and `services/watcher` with matching Compose `build` paths
- Compose: Chroma on host port 8100 (81XX convention); watcher mounts multiple vault paths; middleware reaches host Ollama via `host.docker.internal`

### Fixed

- Taskfile: quote `desc`/`cmds` strings when they contain `: ` or `{{…}}` so YAML/schema validation accepts them

## 2026-04-05

### Added

- Docker Compose stack: ChromaDB, FastAPI RAG server, SillyTavern, and Obsidian vault watcher with shared embedding cache
- FastAPI RAG API for Obsidian: semantic search over the vault, Claude-backed answers, and natural-language → Chroma metadata filters
- Senna middleware layout: shared `models` types, JSON fixtures, and a tiered `validate.py` runner (Tier 1 model tests wired)
- Architecture and validation docs: multi-campaign stack (collections, ST instances, vaults) and tiered test strategy
- Taskfile and SillyTavern config mounts for local UI and plugin data
