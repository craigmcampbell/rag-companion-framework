## Coding

1. Complete Clock Manager (5) + Clock Assessor (6)
Staus: 🔵 In Progress
Finishes current sprint before expanding scope
Clock Assessor establishes the fixture-based AI test pattern for all future AI components

---

2. State Manager (7) + Plot Thread Tracker (14)
Status: ⚪ Open
Both are pure logic — fast to build and test
Define the entity and thread data models consumed by Injector, Planner, and Postgres schema

---

3. Postgres setup + Campaign Router (12)
Status: ⚪ Open
Stand up Postgres with Alembic migrations for all entity tables
Campaign Router establishes isolation before any cross-component integration

---

4. RBAC / Access Control (18)
Status: ⚪ Open
Establish role enforcement early — cheaper to build in than retrofit
Required before MCP server is usable in any meaningful way

---

5. Obsidian Watcher (16) + BM25 Index (15)
Status: ⚪ Open
Watcher feeds ChromaDB (existing), BM25, and Postgres entity tables
Hybrid search now available for Injector

---

6. OpenRouter Client (8) + Injector (9)
Status: ⚪ Open
OpenRouter replaces Ollama as primary generation client
Injector assembles the full augmented prompt — brings all prior components together

---

7. Write-back Pipeline (10) + Middleware Router (11)
Status: ⚪ Open
Closes the generation → vault → watcher → store loop
Middleware Router wires all backend components into a single entry point

---

8. MCP Server (20)
Status: ⚪ Open
TypeScript MCP server wrapping the complete backend
System is now usable from Claude for fast-path RPG queries

---

9. Planner Agent (13)
Status: ⚪ Open
Agentic path added on top of working fast path
Redis session caching for intermediate plan steps

---

10. Observability Logger (17) + Evaluation Engine (19)
Status: ⚪ Open
Wrap the complete request lifecycle with logging
Golden set eval, LLM-as-judge scoring, CLI reporting

---

## Obsidian
○  Review and cleanup campaign vault
