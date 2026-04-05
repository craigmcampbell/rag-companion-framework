# Changelog

## 2026-04-05

### Added

- Docker Compose stack: ChromaDB, FastAPI RAG server, SillyTavern, and Obsidian vault watcher with shared embedding cache
- FastAPI RAG API for Obsidian: semantic search over the vault, Claude-backed answers, and natural-language → Chroma metadata filters
- Senna middleware layout: shared `models` types, JSON fixtures, and a tiered `validate.py` runner (Tier 1 model tests wired)
- Architecture and validation docs: multi-campaign stack (collections, ST instances, vaults) and tiered test strategy
- Taskfile and SillyTavern config mounts for local UI and plugin data
