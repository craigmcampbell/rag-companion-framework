"""
validate.py — Run all component tests in dependency order.

Usage:
  python validate.py           # Tier 1 only (no connections required)
  python validate.py --tier 2  # Tier 1 + 2 (requires Ollama running)
  python validate.py --tier 3  # Full stack (requires all connections)
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests import test_models
from tests import test_chroma_client
from tests import test_ollama_client

# (tier, name, test module)
# Tier 1 = pure logic, no connections
# Tier 2 = requires Ollama (local inference)
# Tier 3 = requires full stack (OpenRouter, ChromaDB, Obsidian)

COMPONENTS = [
    (1, "Data Models",    test_models),
    (1, "ChromaDB Client", test_chroma_client),
    (2, "Ollama Client",   test_ollama_client),
    # Future components added here in build order:
    # (2, "Memory Extractor",    test_memory_extractor),
    # (1, "Clock Manager",       test_clock_manager),
    # (2, "Clock Assessor",      test_clock_assessor),
    # (1, "State Manager",       test_state_manager),
    # (1, "Injector",            test_injector),
    # (2, "Write-back Pipeline", test_writeback_pipeline),
    # (3, "Middleware Router",   test_middleware_router),
]


async def main():
    max_tier = 1
    if "--tier" in sys.argv:
        try:
            max_tier = int(sys.argv[sys.argv.index("--tier") + 1])
        except (IndexError, ValueError):
            print("Usage: python validate.py --tier [1|2|3]")
            sys.exit(1)

    tier_labels = {1: "pure logic", 2: "+ inference", 3: "+ full stack"}
    print(f"=== Senna Middleware Validation (tier {max_tier}: {tier_labels.get(max_tier)}) ===\n")

    passed = 0
    failed = 0
    skipped = 0

    for tier, name, module in COMPONENTS:
        if tier > max_tier:
            print(f"  - {name} (skipped — requires tier {tier})")
            skipped += 1
            continue

        try:
            await module.run()
            print(f"  ✓ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {name}")
            for line in str(e).splitlines():
                print(f"    {line}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {name} (unexpected error)")
            print(f"    {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed  {failed} failed  {skipped} skipped")

    if failed:
        print("\nFix failures before building the next component.")
        sys.exit(1)
    else:
        print("\nAll clear. Safe to proceed.")


asyncio.run(main())