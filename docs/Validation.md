## Three Tiers of Validation

Tier 1 — Unit tests (no connections required)
Pure logic, known inputs, deterministic outputs. Runs anywhere, instantly. This is what we've been designing.

Tier 2 — Inference tests (Ollama running, no OpenRouter spend)
Feed real fixtures to the local model, evaluate the response quality. Not checking for an exact string — checking that the output meets criteria. These run locally and cost nothing.

Tier 3 — Integration tests (full stack live)
End-to-end with real connections. Run rarely — before major changes, after infrastructure updates. The --dry-run mode covers most of what you need here day to day.

### Run Tiers Selectively
```sh
python validate.py           # Tier 1 only — fast, no connections
python validate.py --tier 2  # Tier 1 + 2 — requires Ollama
python validate.py --tier 3  # Full stack
```

## Evaluating Model Output

AI output isn't deterministic, so classical assertions don't work:
```python
# This will randomly fail even when working correctly
assert extracted["events"][0] == "Garion paid the contact the agreed amount"
```

Instead you evaluate against criteria:
```python
async def evaluate_extraction(extracted: dict, exchange: dict) -> dict:
    prompt = f"""
      You are evaluating whether a memory extraction is working correctly.

      Original exchange:
      User: {exchange['user']}
      Assistant: {exchange['assistant']}

      Extracted memory:
      {json.dumps(extracted, indent=2)}

      Evaluate against these criteria. Return JSON only:
      {{
        "captures_key_event": true/false,
        "no_hallucinated_facts": true/false,
        "appropriate_detail_level": true/false,
        "missed_anything_important": true/false,
        "missed_details": "description or null",
        "overall_pass": true/false,
        "notes": "brief explanation"
      }}
      """
      
    response = await ollama_complete(prompt)
    return json.loads(response)
```

The model evaluates the model's output. Works surprisingly well for this kind of structured quality check.

### Handling Non-Determinism

For tier 2 tests, run each inference check three times and require it passes at least two of three. Filters out random variance without masking genuine failures:

```python
async def inference_check(test_fn, runs=3, threshold=2):
  results = []
  for _ in range(runs):
      result = await test_fn()
      results.append(result)
  
  passed = sum(1 for r in results if r["overall_pass"])
  return {
      "passed": passed >= threshold,
      "score": f"{passed}/{runs}",
      "results": results
  }
```

If your extractor passes 2/3 runs it's working. If it's passing 1/3 something is wrong with the prompt, not random variance.
