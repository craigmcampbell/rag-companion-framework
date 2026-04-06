"""
memory_extractor.py — Extracts structured memories from conversation exchanges.

Responsibilities:
- Filter exchanges that aren't worth remembering (memorability check)
- Extract events, revelations, state changes, and notable quotes
- Classify significance (normal / high / milestone)
- Return strongly-typed ExtractedMemory objects

Campaign-specific context (character names, setting, relationship) is
injected via CampaignContext — the extractor itself is fully generic.

Does NOT:
- Write to ChromaDB or Obsidian (that's the write-back pipeline)
- Know anything about clocks or state (separate components)
- Make decisions about injection (that's the injector)
"""

from __future__ import annotations

from components.models import Exchange, ExtractedMemory, MemorySignificance
from components.ollama_client import OllamaClient, OllamaJSONError
from components.campaign_context import CampaignContext

import logging
logger = logging.getLogger(__name__)


# ── Memorability filter ───────────────────────────────────────────────────────

# Universal storytelling signal words — campaign-agnostic.
# These suggest something worth remembering happened regardless of setting.
_SIGNAL_WORDS = {
    "remember", "always", "never", "first time", "finally",
    "realized", "decided", "found", "lost", "told", "secret",
    "promised", "bought", "discovered", "breakthrough", "solved",
    "admitted", "asked", "answered", "agreed", "refused",
    "milestone", "important", "significant", "finally said",
    "never told", "almost", "dangerous", "worried", "afraid",
}

# Milestone phrases — if any appear the exchange is automatically elevated
_MILESTONE_PHRASES = {
    "first time", "never told", "almost lost", "finally said",
    "bought", "breakthrough", "i love", "never said", "i'm sorry",
    "forgive", "can't lose", "don't want to lose", "solved",
}


def is_memorable(exchange: Exchange) -> bool:
    """
    Lightweight heuristic check before spending inference on extraction.

    Returns True if the exchange contains signal words suggesting
    something worth remembering happened. Domestic small talk returns False.

    Intentionally permissive — false negatives (missing something
    important) are worse than false positives (extracting something minor).
    """
    combined = (exchange.user + " " + exchange.assistant).lower()
    return any(signal in combined for signal in _SIGNAL_WORDS)


def has_milestone_signal(exchange: Exchange) -> bool:
    """
    Check if an exchange contains milestone-level phrases.
    Used to pre-classify significance before inference.
    """
    combined = (exchange.user + " " + exchange.assistant).lower()
    return any(phrase in combined for phrase in _MILESTONE_PHRASES)


# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a memory extraction system for an ongoing roleplay story.
Your role is to identify what is worth remembering from a conversation exchange.
You return only valid JSON with no explanation, preamble, or markdown formatting."""

_EXTRACTION_PROMPT = """Extract long-term memories from this roleplay exchange.

{campaign_preamble}

Exchange:
User ({user_name}): {user}
Assistant ({companion_name}): {assistant}

Extract only what is genuinely worth remembering long-term. Skip routine conversation.

Return this exact JSON structure:
{{
  "events": ["list of concrete things that happened, empty if nothing notable"],
  "revelations": ["list of things learned or discovered, empty if none"],
  "state_changes": ["list of how characters or their situation shifted, empty if none"],
  "notable_quote": "one memorable line worth preserving verbatim, or null",
  "significance": "normal or high or milestone",
  "worth_remembering": true or false
}}

Significance guide:
- normal: worth keeping but routine story content
- high: important event that will likely matter later
- milestone: defining moment in the relationship or story (rare)

Return JSON only."""


# ── Extractor ─────────────────────────────────────────────────────────────────

class MemoryExtractor:
    """
    Extracts structured memories from conversation exchanges.

    Generic — all campaign-specific context comes from CampaignContext.

    Typical usage:
        extractor = MemoryExtractor(ollama_client, campaign_context)
        memory = await extractor.extract(exchange)
        if memory and not memory.is_empty():
            # write to Obsidian / ChromaDB
    """

    def __init__(self, ollama: OllamaClient, campaign: CampaignContext):
        self.ollama = ollama
        self.campaign = campaign

    async def extract(self, exchange: Exchange) -> ExtractedMemory | None:
        """
        Extract a memory from an exchange.

        Returns None if the exchange fails the memorability filter.
        Returns an ExtractedMemory (possibly empty) if it passes.

        The caller should check memory.is_empty() before writing.
        """
        if not is_memorable(exchange):
            return None

        prompt = _EXTRACTION_PROMPT.format(
            campaign_preamble=self.campaign.prompt_preamble,
            user_name=self.campaign.user_character.name,
            companion_name=self.campaign.companion_character.name,
            user=exchange.user,
            assistant=exchange.assistant,
        )

        try:
            raw = await self.ollama.generate_json(
                prompt=prompt,
                system=_SYSTEM_PROMPT,
            )
        except OllamaJSONError as e:
            logger.warning("[MemoryExtractor] JSON parse failed: %s", e)
            return ExtractedMemory()

        if not raw.get("worth_remembering", True):
            return ExtractedMemory()

        significance_str = raw.get("significance", "normal")
        if has_milestone_signal(exchange) and significance_str == "normal":
            significance_str = "high"

        try:
            significance = MemorySignificance(significance_str)
        except ValueError:
            significance = MemorySignificance.NORMAL

        return ExtractedMemory(
            events=_clean_list(raw.get("events", [])),
            revelations=_clean_list(raw.get("revelations", [])),
            state_changes=_clean_list(raw.get("state_changes", [])),
            notable_quote=raw.get("notable_quote") or None,
            significance=significance,
        )

    async def extract_batch(
        self, exchanges: list[Exchange]
    ) -> list[tuple[Exchange, ExtractedMemory | None]]:
        """
        Extract memories from multiple exchanges sequentially.
        Returns paired (exchange, memory) tuples.
        """
        results = []
        for exchange in exchanges:
            memory = await self.extract(exchange)
            results.append((exchange, memory))
        return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_list(value: object) -> list[str]:
    """Normalize model output that should be a list of strings."""
    if not value:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if item and str(item).strip()]
    return []