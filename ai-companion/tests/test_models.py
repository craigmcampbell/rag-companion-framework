"""
test_models.py — Tier 1 tests for data models.

No connections required. All inputs and outputs are deterministic.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.models import (
    Message, Exchange, ExtractedMemory, RetrievedMemory,
    Clock, ClockAssessment, ClockType, ClockSurface,
    CharacterState, ResearchState, RelationshipState,
    WorldState, InjectionContext, EvaluationResult,
    MemorySignificance, Mood, EnergyLevel,
)


def test_message_roundtrip():
    msg = Message(role="user", content="Tell me you got it.")
    assert Message.from_dict(msg.to_dict()) == msg


def test_exchange_roundtrip():
    ex = Exchange(
        user="The contact wanted double.",
        assistant="Senna looked up. 'You did right.'",
        session_date="2024-03-15",
    )
    restored = Exchange.from_dict(ex.to_dict())
    assert restored.user == ex.user
    assert restored.assistant == ex.assistant
    assert restored.session_date == ex.session_date


def test_extracted_memory_empty():
    mem = ExtractedMemory()
    assert mem.is_empty()


def test_extracted_memory_not_empty():
    mem = ExtractedMemory(events=["Garion paid the contact the agreed amount"])
    assert not mem.is_empty()


def test_extracted_memory_markdown_lines():
    mem = ExtractedMemory(
        events=["Garion returned from the job"],
        revelations=["The contact was testing Garion"],
        state_changes=["Senna's trust in Garion increased"],
        notable_quote="You're getting better at reading people.",
    )
    lines = mem.to_markdown_lines()
    assert any("Garion returned" in l for l in lines)
    assert any("REVEALED" in l for l in lines)
    assert any("STATE" in l for l in lines)
    assert any("getting better" in l for l in lines)


def test_extracted_memory_roundtrip():
    mem = ExtractedMemory(
        events=["Garion paid correctly"],
        significance=MemorySignificance.HIGH,
    )
    restored = ExtractedMemory.from_dict(mem.to_dict())
    assert restored.events == mem.events
    assert restored.significance == mem.significance


def test_clock_increment_no_trigger():
    clock = Clock(
        id="test", name="Test Clock", clock_type=ClockType.THREAT,
        segments=6, filled=2, description="", trigger_effect=""
    )
    triggered = clock.increment()
    assert not triggered
    assert clock.filled == 3


def test_clock_increment_triggers():
    clock = Clock(
        id="test", name="Test Clock", clock_type=ClockType.THREAT,
        segments=6, filled=5, description="", trigger_effect=""
    )
    triggered = clock.increment()
    assert triggered
    assert clock.is_full
    assert clock.triggered


def test_clock_increment_caps_at_segments():
    clock = Clock(
        id="test", name="Test Clock", clock_type=ClockType.THREAT,
        segments=6, filled=6, description="", trigger_effect=""
    )
    clock.increment()
    assert clock.filled == 6


def test_clock_decrement_resets_triggered():
    clock = Clock(
        id="test", name="Test Clock", clock_type=ClockType.THREAT,
        segments=6, filled=6, description="", trigger_effect="",
        triggered=True
    )
    clock.decrement()
    assert not clock.triggered
    assert clock.filled == 5


def test_clock_decrement_floors_at_zero():
    clock = Clock(
        id="test", name="Test Clock", clock_type=ClockType.THREAT,
        segments=6, filled=0, description="", trigger_effect=""
    )
    clock.decrement()
    assert clock.filled == 0


def test_clock_progress_ratio():
    clock = Clock(
        id="test", name="Test Clock", clock_type=ClockType.PROGRESS,
        segments=4, filled=2, description="", trigger_effect=""
    )
    assert clock.progress_ratio == 0.5


def test_clock_roundtrip():
    clock = Clock(
        id="compact_investigation",
        name="The Compact Closes In",
        clock_type=ClockType.THREAT,
        segments=6,
        filled=2,
        description="The Compact suspects unlicensed work",
        trigger_effect="An investigator makes direct contact",
        increment_conditions=["Senna uses magic publicly"],
        visible_to_players=False,
    )
    restored = Clock.from_dict(clock.to_dict())
    assert restored.id == clock.id
    assert restored.clock_type == clock.clock_type
    assert restored.visible_to_players == clock.visible_to_players
    assert restored.increment_conditions == clock.increment_conditions


def test_clock_assessment_has_changes_false():
    assessment = ClockAssessment()
    assert not assessment.has_changes()


def test_clock_assessment_has_changes_true():
    assessment = ClockAssessment(increments=[{"id": "test", "reason": "job went loud"}])
    assert assessment.has_changes()


def test_clock_assessment_roundtrip():
    assessment = ClockAssessment(
        increments=[{"id": "compact_investigation", "reason": "job went loud"}],
        surface_now=True,
    )
    restored = ClockAssessment.from_dict(assessment.to_dict())
    assert restored.increments == assessment.increments
    assert restored.surface_now == assessment.surface_now


def test_character_state_prompt_fragment_no_tension():
    state = CharacterState(mood=Mood.FOCUSED, energy=EnergyLevel.LOW)
    fragment = state.to_prompt_fragment()
    assert "focused" in fragment
    assert "low" in fragment
    assert "tension" not in fragment.lower()


def test_character_state_prompt_fragment_with_tension():
    state = CharacterState(tension_with_garion="mild")
    fragment = state.to_prompt_fragment()
    assert "mild" in fragment


def test_character_state_roundtrip():
    state = CharacterState(
        mood=Mood.EXCITED,
        energy=EnergyLevel.HIGH,
        research_excitement="high",
        tension_with_garion="none",
    )
    restored = CharacterState.from_dict(state.to_dict())
    assert restored.mood == state.mood
    assert restored.energy == state.energy


def test_research_state_prompt_fragment():
    state = ResearchState(
        progress=45,
        current_obstacle="stabilizing intent-to-effect translation",
        materials_needed=["resonance crystal"],
    )
    fragment = state.to_prompt_fragment()
    assert "45%" in fragment
    assert "stabilizing" in fragment
    assert "resonance crystal" in fragment


def test_research_state_roundtrip():
    state = ResearchState(
        progress=34,
        current_obstacle="component resonance",
        materials_needed=["resonance crystal", "Aldric vol. 3"],
    )
    restored = ResearchState.from_dict(state.to_dict())
    assert restored.progress == state.progress
    assert restored.materials_needed == state.materials_needed


def test_relationship_state_roundtrip():
    state = RelationshipState(
        trust=87,
        tension=12,
        last_significant_moment="Garion admitted the job cost more than he said",
        unspoken_things=["the future", "how close that was"],
    )
    restored = RelationshipState.from_dict(state.to_dict())
    assert restored.trust == state.trust
    assert restored.unspoken_things == state.unspoken_things


def test_injection_context_has_content_empty():
    ctx = InjectionContext()
    assert not ctx.has_content()


def test_injection_context_has_content_with_memories():
    ctx = InjectionContext(
        retrieved_memories=[
            RetrievedMemory(
                content="Garion retrieved the Aldric Codex",
                source="Sessions/2024-03-15.md",
                significance=MemorySignificance.HIGH,
                distance=0.12,
            )
        ]
    )
    assert ctx.has_content()


def test_injection_context_has_content_with_clock_effect():
    ctx = InjectionContext(pending_clock_effect="A stranger has been watching the shop.")
    assert ctx.has_content()


def test_evaluation_result_roundtrip():
    result = EvaluationResult(
        passed=True,
        criteria_results={"captures_key_event": True, "no_hallucinations": True},
        notes="Clean extraction",
        score="3/3",
    )
    restored = EvaluationResult.from_dict(result.to_dict())
    assert restored.passed == result.passed
    assert restored.score == result.score
    assert restored.criteria_results == result.criteria_results


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

async def run(tier: int = 1):
    # tier parameter accepted for interface consistency with other test modules.
    # test_models has no tier 2/3 checks — all tests are pure logic.
    tests = [
        test_message_roundtrip,
        test_exchange_roundtrip,
        test_extracted_memory_empty,
        test_extracted_memory_not_empty,
        test_extracted_memory_markdown_lines,
        test_extracted_memory_roundtrip,
        test_clock_increment_no_trigger,
        test_clock_increment_triggers,
        test_clock_increment_caps_at_segments,
        test_clock_decrement_resets_triggered,
        test_clock_decrement_floors_at_zero,
        test_clock_progress_ratio,
        test_clock_roundtrip,
        test_clock_assessment_has_changes_false,
        test_clock_assessment_has_changes_true,
        test_clock_assessment_roundtrip,
        test_character_state_prompt_fragment_no_tension,
        test_character_state_prompt_fragment_with_tension,
        test_character_state_roundtrip,
        test_research_state_prompt_fragment,
        test_research_state_roundtrip,
        test_relationship_state_roundtrip,
        test_injection_context_has_content_empty,
        test_injection_context_has_content_with_memories,
        test_injection_context_has_content_with_clock_effect,
        test_evaluation_result_roundtrip,
    ]

    failed = []
    for test in tests:
        try:
            test()
        except Exception as e:
            failed.append((test.__name__, str(e)))

    if failed:
        msg = "\n".join(f"  {name}: {err}" for name, err in failed)
        raise AssertionError(f"{len(failed)} test(s) failed:\n{msg}")