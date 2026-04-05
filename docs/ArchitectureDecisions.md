Multi-Campaign AI Companion Stack — Architecture Decisions
Problem
Needed clean separation between two TTRPG campaigns (Senna fantasy scholar-mage and Starforged prequel) without duplicating the entire infrastructure.
SillyTavern

Two separate ST instances running in Docker containers on different ports
Each instance is fully isolated — separate character cards, lorebooks, system prompts, UI state
System prompts live in character cards, not globally — global prompt stays minimal or empty
Lorebooks scoped to chat, not global

Shared Infrastructure (single instance each)

ChromaDB — shared instance, campaigns separated by named collections (senna_memory, starforged_memory)
Ollama — stateless, shared trivially
FastAPI RAG middleware — shared, made collection-aware via config/query param so each ST instance routes to its own collection

Obsidian Vaults

Two separate vaults maintained (preferred for clean separation)
Already using Obsidian Sync — vaults replicate to always-on machine automatically

Watcher

Single watcher container using Option A — multi-vault config with (path, collection) pairs
Both vaults mounted read-only into the container
Config driven:

```yaml
vaults:
  - path: /vaults/senna
    collection: senna_memory
  - path: /vaults/starforged
    collection: starforged_memory
```

Key Architectural Principle
collection_name is a first-class config value throughout the middleware — adding a third campaign in the future is just a new vault mount, a new collection, and a new ST container.
