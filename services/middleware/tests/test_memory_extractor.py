"""
test_memory_extractor.py — Tests for the memory extractor.

Tier 1: Pure logic tests — memorability filter, significance classification,
         output normalization. No inference required.

Tier 2: Live inference tests using real fixtures. Validates that
         mistral-nemo:12b extracts correctly from known exchanges and
         correctly identifies low-signal exchanges as not worth extracting.
         Uses 2/3 pass threshold for non-determinism.
"""

import sys
import os
import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.models import Exchange, ExtractedMemory, MemorySignificance
from components.ollama_client import OllamaClient
from components.campaign_context import CampaignContext, CharacterConfig
from components.memory_extractor import (
    MemoryExtractor,
    is_memorable,
    has_milestone_signal,
    _clean_list,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "exchanges"
CAMPAIGN_DIR = Path(__file__).parent.parent / "campaigns"


def load_exchange(filename: str) -> Exchange:
    with open(FIXTURE_DIR / filename) as f:
        return Exchange.from_dict(json.load(f))


def make_test_campaign() -> CampaignContext:
    """
    Minimal generic campaign context for tier 1 tests.
    Does not reference Senna or Garion by name — tests stay generic.
    """
    return CampaignContext(
        campaign_id="test_memory",
        campaign_name="Test Campaign",
        genre="fantasy",
        user_character=CharacterConfig(
            name="Player",
            role="operative",
        ),
        companion_character=CharacterConfig(
            name="Companion",
            role="scholar",
        ),
        relationship="Long-term partners, professional and romantic.",
        setting="A fictional trade city.",
    )


def make_mock_ollama(json_response: dict[str, Any]) -> OllamaClient:
    mock = AsyncMock(spec=OllamaClient)
    mock.generate_json = AsyncMock(return_value=json_response)
    return mock


# ── Tier 1: Memorability filter ───────────────────────────────────────────────

def test_memorable_job_return():
    ex = load_exchange("job_return.json")
    assert is_memorable(ex) is True


def test_not_memorable_domestic():
    ex = load_exchange("domestic_quiet.json")
    assert is_memorable(ex) is False


def test_memorable_breakthrough():
    ex = load_exchange("research_breakthrough.json")
    assert is_memorable(ex) is True


def test_memorable_explicit_signal_word():
    ex = Exchange(user="I promised I'd come back.", assistant="She didn't say anything.")
    assert is_memorable(ex) is True


def test_not_memorable_small_talk():
    ex = Exchange(user="How's the weather?", assistant="Cloudy. As usual.")
    assert is_memorable(ex) is False


# ── Tier 1: Milestone signal detection ───────────────────────────────────────

def test_milestone_signal_first_time():
    ex = Exchange(
        user="This is the first time I've seen you actually stop working.",
        assistant="Don't get used to it.",
    )
    assert has_milestone_signal(ex) is True


def test_milestone_signal_breakthrough():
    ex = load_exchange("research_breakthrough.json")
    assert has_milestone_signal(ex) is True


def test_no_milestone_signal_routine():
    ex = load_exchange("job_return.json")
    assert has_milestone_signal(ex) is False


# ── Tier 1: _clean_list normalization ─────────────────────────────────────────

def test_clean_list_normal():
    assert _clean_list(["event one", "event two"]) == ["event one", "event two"]


def test_clean_list_none():
    assert _clean_list(None) == []


def test_clean_list_empty_list():
    assert _clean_list([]) == []


def test_clean_list_single_string():
    assert _clean_list("single event") == ["single event"]


def test_clean_list_filters_empty_strings():
    assert _clean_list(["valid", "", "  ", "also valid"]) == ["valid", "also valid"]


def test_clean_list_coerces_non_strings():
    assert _clean_list([1, 2, "three"]) == ["1", "2", "three"]


# ── Tier 1: CampaignContext ───────────────────────────────────────────────────

def test_campaign_context_prompt_preamble_contains_names():
    ctx = make_test_campaign()
    preamble = ctx.prompt_preamble
    assert "Player" in preamble
    assert "Companion" in preamble
    assert "fantasy" in preamble


def test_campaign_context_loads_from_yaml():
    ctx = CampaignContext.from_yaml(CAMPAIGN_DIR / "senna.yml")
    assert ctx.campaign_id == "senna_memory"
    assert ctx.user_character.name == "Garion"
    assert ctx.companion_character.name == "Senna"


def test_campaign_context_starforged_loads():
    ctx = CampaignContext.from_yaml(CAMPAIGN_DIR / "starforged.yml")
    assert ctx.campaign_id == "starforged_memory"
    assert ctx.user_character.name == "Brennan"


def test_campaign_context_roundtrip():
    ctx = make_test_campaign()
    d = ctx.to_dict()
    assert d["campaign_id"] == "test_memory"
    assert d["user_character"]["name"] == "Player"


# ── Tier 1: Extractor with mocked Ollama ─────────────────────────────────────

async def test_extract_returns_none_for_non_memorable():
    ollama = make_mock_ollama({})
    extractor = MemoryExtractor(ollama, make_test_campaign())
    ex = load_exchange("domestic_quiet.json")
    result = await extractor.extract(ex)
    assert result is None
    cast(AsyncMock, ollama.generate_json).assert_not_called()


async def test_extract_returns_empty_when_model_says_not_worth_it():
    ollama = make_mock_ollama({"worth_remembering": False})
    extractor = MemoryExtractor(ollama, make_test_campaign())
    ex = load_exchange("job_return.json")
    result = await extractor.extract(ex)
    assert result is not None
    assert result.is_empty()


async def test_extract_populates_fields():
    ollama = make_mock_ollama({
        "worth_remembering": True,
        "events": ["Player paid the contact correctly"],
        "revelations": ["The contact was testing Player"],
        "state_changes": ["Companion's confidence in Player increased"],
        "notable_quote": "He was testing you. You did right.",
        "significance": "normal",
    })
    extractor = MemoryExtractor(ollama, make_test_campaign())
    ex = load_exchange("job_return.json")
    result = await extractor.extract(ex)
    assert result is not None
    assert len(result.events) == 1
    assert result.notable_quote is not None
    assert result.significance == MemorySignificance.NORMAL


async def test_extract_upgrades_significance_on_milestone_signal():
    ollama = make_mock_ollama({
        "worth_remembering": True,
        "events": ["Companion solved the resonance problem"],
        "revelations": ["Components match caster, not spell"],
        "state_changes": [],
        "notable_quote": None,
        "significance": "normal",
    })
    extractor = MemoryExtractor(ollama, make_test_campaign())
    ex = load_exchange("research_breakthrough.json")
    result = await extractor.extract(ex)
    assert result is not None
    assert result.significance == MemorySignificance.HIGH


async def test_extract_respects_milestone_significance():
    ollama = make_mock_ollama({
        "worth_remembering": True,
        "events": ["They bought the house"],
        "revelations": [],
        "state_changes": ["Characters have a permanent home"],
        "notable_quote": None,
        "significance": "milestone",
    })
    extractor = MemoryExtractor(ollama, make_test_campaign())
    ex = Exchange(
        user="We bought it. The house.",
        assistant="She was quiet for a long moment. 'I know,' she said finally."
    )
    result = await extractor.extract(ex)
    assert result is not None
    assert result.significance == MemorySignificance.MILESTONE


async def test_extract_handles_json_error_gracefully():
    from components.ollama_client import OllamaJSONError
    ollama = AsyncMock(spec=OllamaClient)
    ollama.generate_json = AsyncMock(side_effect=OllamaJSONError("parse failed"))
    extractor = MemoryExtractor(ollama, make_test_campaign())
    ex = load_exchange("job_return.json")
    result = await extractor.extract(ex)
    assert result is not None
    assert result.is_empty()


async def test_extract_prompt_uses_campaign_character_names():
    """Verify the prompt template uses campaign config names, not hardcoded ones."""
    ollama = make_mock_ollama({
        "worth_remembering": True,
        "events": ["something happened"],
        "revelations": [],
        "state_changes": [],
        "notable_quote": None,
        "significance": "normal",
    })
    extractor = MemoryExtractor(ollama, make_test_campaign())
    ex = load_exchange("job_return.json")
    await extractor.extract(ex)

    mock = cast(AsyncMock, ollama.generate_json)
    call_args = mock.call_args
    kwargs = call_args.kwargs if call_args.kwargs else call_args[1]
    prompt = kwargs.get("prompt", "")

    # The prompt preamble and exchange labels should use campaign config names
    assert "Player" in prompt
    assert "Companion" in prompt

    # The prompt structure labels should not have hardcoded names.
    # We verify this by checking that "User (Player):" and
    # "Assistant (Companion):" appear as the exchange labels —
    # if hardcoded, they'd say "User (Garion):" instead.
    assert "User (Player):" in prompt
    assert "Assistant (Companion):" in prompt


async def test_extract_batch_filters_non_memorable():
    ollama = make_mock_ollama({
        "worth_remembering": True,
        "events": ["notable event"],
        "revelations": [],
        "state_changes": [],
        "notable_quote": None,
        "significance": "normal",
    })
    extractor = MemoryExtractor(ollama, make_test_campaign())
    exchanges = [
        load_exchange("job_return.json"),
        load_exchange("domestic_quiet.json"),
        load_exchange("research_breakthrough.json"),
    ]
    results = await extractor.extract_batch(exchanges)
    assert cast(AsyncMock, ollama.generate_json).call_count == 2
    assert results[1][1] is None  # domestic quiet filtered


# ── Tier 2: Live inference ────────────────────────────────────────────────────

async def run_live_inference():
    """
    Requires Ollama running with mistral-nemo:12b.
    Uses the real Senna campaign config — validates against actual campaign context.
    Runs each check 3 times, requires 2/3 passes.
    """
    client = OllamaClient()
    try:
        campaign = CampaignContext.from_yaml(CAMPAIGN_DIR / "senna.yml")
        extractor = MemoryExtractor(client, campaign)

        async def check_job_return() -> dict[str, Any]:
            ex = load_exchange("job_return.json")
            result = await extractor.extract(ex)
            return {
                "overall_pass": (
                    result is not None
                    and not result.is_empty()
                    and len(result.events) > 0
                ),
                "notes": f"events={result.events if result else None}",
            }

        async def check_domestic_filtered() -> dict[str, Any]:
            ex = load_exchange("domestic_quiet.json")
            result = await extractor.extract(ex)
            return {
                "overall_pass": result is None,
                "notes": f"result={'None (correct)' if result is None else 'not None (wrong)'}",
            }

        async def check_breakthrough_significance() -> dict[str, Any]:
            ex = load_exchange("research_breakthrough.json")
            result = await extractor.extract(ex)
            passed = (
                result is not None
                and not result.is_empty()
                and result.significance in (MemorySignificance.HIGH, MemorySignificance.MILESTONE)
            )
            return {
                "overall_pass": passed,
                "notes": f"significance={result.significance if result else None}",
            }

        checks = [
            ("Job return extracts events",            check_job_return),
            ("Domestic quiet filtered pre-inference", check_domestic_filtered),
            ("Breakthrough classified high+",         check_breakthrough_significance),
        ]

        failures = []
        for check_name, check_fn in checks:
            results = []
            for _ in range(3):
                r = await check_fn()
                results.append(r)

            passed = sum(1 for r in results if r["overall_pass"])
            if passed < 2:
                notes = [r["notes"] for r in results]
                failures.append(f"{check_name} ({passed}/3): {notes}")

        if failures:
            raise AssertionError(
                "Tier 2 inference checks failed:\n" +
                "\n".join(f"  - {f}" for f in failures)
            )
    finally:
        await client.close()


# ── Test runner ───────────────────────────────────────────────────────────────

async def run(tier: int = 1):
    sync_tests = [
        test_memorable_job_return,
        test_not_memorable_domestic,
        test_memorable_breakthrough,
        test_memorable_explicit_signal_word,
        test_not_memorable_small_talk,
        test_milestone_signal_first_time,
        test_milestone_signal_breakthrough,
        test_no_milestone_signal_routine,
        test_clean_list_normal,
        test_clean_list_none,
        test_clean_list_empty_list,
        test_clean_list_single_string,
        test_clean_list_filters_empty_strings,
        test_clean_list_coerces_non_strings,
        test_campaign_context_prompt_preamble_contains_names,
        test_campaign_context_loads_from_yaml,
        test_campaign_context_starforged_loads,
        test_campaign_context_roundtrip,
    ]

    async_tests = [
        test_extract_returns_none_for_non_memorable,
        test_extract_returns_empty_when_model_says_not_worth_it,
        test_extract_populates_fields,
        test_extract_upgrades_significance_on_milestone_signal,
        test_extract_respects_milestone_significance,
        test_extract_handles_json_error_gracefully,
        test_extract_prompt_uses_campaign_character_names,
        test_extract_batch_filters_non_memorable,
    ]

    failed = []

    for test in sync_tests:
        try:
            test()
        except Exception as e:
            failed.append((test.__name__, repr(e)))

    for test in async_tests:
        try:
            await test()
        except Exception as e:
            failed.append((test.__name__, repr(e)))

    if failed:
        msg = "\n".join(f"  {name}: {err}" for name, err in failed)
        raise AssertionError(f"{len(failed)} tier 1 test(s) failed:\n{msg}")

    if tier >= 2:
        await run_live_inference()