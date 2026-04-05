## Coding

| Status | Component               |                                             |
| ------ | ----------------------- | ------------------------------------------- |
| 🟢     | 1. Data Models          | ← shared types everything else depends on   |
| 🔵      | 2. ChromaDB Client      | ← retrieval, isolated                       |
| ○      | 3. Ollama Client        | ← local inference, isolated                 |
| ○      | 4. Memory Extractor     | ← uses Ollama, testable with fixtures       |
| ○      | 5. Clock Manager        | ← pure logic, no AI dependency              |
| ○      | 6. Clock Assessor       | ← uses Ollama, testable with fixtures       |
| ○      | 7. State Manager        | ← emotional/relationship state, pure logic  |
| ○      | 8. OpenRouter Client    | ← forward/receive, isolated                 |
| ○      | 9. Injector             | ← builds augmented prompts, pure logic      |
| ○      | 10. Write-back Pipeline | ← orchestrates 3,4,6,7, testable end-to-end |
| ○      | 11. Middleware Router   | ← wires everything, integration tested      |


## Obsidian
○  Review and cleanup campaign vault
