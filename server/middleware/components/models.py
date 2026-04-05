"""
models.py — Shared data models for the Senna middleware.

All components import from here. If a type needs to change,
it changes in one place.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import json
from datetime import datetime


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MemorySignificance(str, Enum):
    LOW = "low"          # Routine exchange, background texture
    NORMAL = "normal"    # Worth keeping, standard session content
    HIGH = "high"        # Important event, should always be retrievable
    MILESTONE = "milestone"  # Defining moment, never drops from retrieval


class ClockType(str, Enum):
    THREAT = "threat"          # Gets bad if ignored
    OPPORTUNITY = "opportunity" # Closes if not pursued
    PROGRESS = "progress"      # Long-term goal with visible momentum
    RELATIONSHIP = "relationship"  # Unresolved tension between characters
    WORLD = "world"            # World events independent of the story


class ClockSurface(str, Enum):
    HARD = "hard"   # Inject effect immediately and directly
    SOFT = "soft"   # Inject a hint; let effect unfold naturally


class Mood(str, Enum):
    FOCUSED = "focused"
    DISTRACTED = "distracted"
    EXCITED = "excited"
    TIRED = "tired"
    TENSE = "tense"
    CONTENT = "content"
    WORRIED = "worried"
    PLAYFUL = "playful"


class EnergyLevel(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    DEPLETED = "depleted"


# ---------------------------------------------------------------------------
# Core exchange types
# ---------------------------------------------------------------------------

@dataclass
class Message:
    """A single message in the conversation."""
    role: str           # "user" or "assistant"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}

    @classmethod
    def from_dict(cls, d: dict) -> Message:
        return cls(role=d["role"], content=d["content"])


@dataclass
class Exchange:
    """
    A matched user/assistant pair.
    The fundamental unit of memory extraction and clock assessment.
    """
    user: str
    assistant: str
    session_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "user": self.user,
            "assistant": self.assistant,
            "session_date": self.session_date,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Exchange:
        return cls(
            user=d["user"],
            assistant=d["assistant"],
            session_date=d.get("session_date", datetime.now().strftime("%Y-%m-%d")),
            timestamp=d.get("timestamp", datetime.now().isoformat()),
        )


# ---------------------------------------------------------------------------
# Memory types
# ---------------------------------------------------------------------------

@dataclass
class ExtractedMemory:
    """
    Structured output from the memory extractor.
    One of these is produced per exchange that passes the memorability filter.
    """
    events: list[str] = field(default_factory=list)
    revelations: list[str] = field(default_factory=list)
    state_changes: list[str] = field(default_factory=list)
    notable_quote: Optional[str] = None
    significance: MemorySignificance = MemorySignificance.NORMAL

    def is_empty(self) -> bool:
        return not any([self.events, self.revelations, self.state_changes])

    def to_markdown_lines(self) -> list[str]:
        """Format for appending to an Obsidian session note."""
        lines = []
        for event in self.events:
            lines.append(f"- {event}")
        for revelation in self.revelations:
            lines.append(f"- REVEALED: {revelation}")
        for change in self.state_changes:
            lines.append(f"- STATE: {change}")
        if self.notable_quote:
            lines.append(f'\n> "{self.notable_quote}"\n')
        return lines

    def to_dict(self) -> dict:
        return {
            "events": self.events,
            "revelations": self.revelations,
            "state_changes": self.state_changes,
            "notable_quote": self.notable_quote,
            "significance": self.significance.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ExtractedMemory:
        return cls(
            events=d.get("events", []),
            revelations=d.get("revelations", []),
            state_changes=d.get("state_changes", []),
            notable_quote=d.get("notable_quote"),
            significance=MemorySignificance(d.get("significance", "normal")),
        )


@dataclass
class RetrievedMemory:
    """A memory returned from ChromaDB with its source metadata."""
    content: str
    source: str          # Obsidian file path
    significance: MemorySignificance
    distance: float      # Semantic distance — lower is more relevant
    session_date: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "source": self.source,
            "significance": self.significance.value,
            "distance": self.distance,
            "session_date": self.session_date,
        }


# ---------------------------------------------------------------------------
# Clock types
# ---------------------------------------------------------------------------

@dataclass
class Clock:
    """
    A tension clock. Tracks a narrative pressure that builds over time.
    """
    id: str
    name: str
    clock_type: ClockType
    segments: int
    filled: int
    description: str
    trigger_effect: str
    increment_conditions: list[str] = field(default_factory=list)
    decrement_conditions: list[str] = field(default_factory=list)
    visible_to_players: bool = True
    triggered: bool = False
    created_session: Optional[str] = None

    @property
    def is_full(self) -> bool:
        return self.filled >= self.segments

    @property
    def progress_ratio(self) -> float:
        return self.filled / self.segments

    def increment(self, amount: int = 1) -> bool:
        """Returns True if this increment triggered the clock."""
        self.filled = min(self.filled + amount, self.segments)
        if self.is_full and not self.triggered:
            self.triggered = True
            return True
        return False

    def decrement(self, amount: int = 1) -> None:
        self.filled = max(self.filled - amount, 0)
        if not self.is_full:
            self.triggered = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "clock_type": self.clock_type.value,
            "segments": self.segments,
            "filled": self.filled,
            "description": self.description,
            "trigger_effect": self.trigger_effect,
            "increment_conditions": self.increment_conditions,
            "decrement_conditions": self.decrement_conditions,
            "visible_to_players": self.visible_to_players,
            "triggered": self.triggered,
            "created_session": self.created_session,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Clock:
        return cls(
            id=d["id"],
            name=d["name"],
            clock_type=ClockType(d["clock_type"]),
            segments=d["segments"],
            filled=d["filled"],
            description=d["description"],
            trigger_effect=d["trigger_effect"],
            increment_conditions=d.get("increment_conditions", []),
            decrement_conditions=d.get("decrement_conditions", []),
            visible_to_players=d.get("visible_to_players", True),
            triggered=d.get("triggered", False),
            created_session=d.get("created_session"),
        )


@dataclass
class ClockAssessment:
    """Structured output from the clock assessor."""
    increments: list[dict] = field(default_factory=list)   # [{"id": ..., "reason": ...}]
    decrements: list[dict] = field(default_factory=list)
    triggered: list[dict] = field(default_factory=list)    # [{"id": ..., "effect": ..., "surface": ...}]
    surface_now: bool = False

    def has_changes(self) -> bool:
        return bool(self.increments or self.decrements or self.triggered)

    def to_dict(self) -> dict:
        return {
            "increments": self.increments,
            "decrements": self.decrements,
            "triggered": self.triggered,
            "surface_now": self.surface_now,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ClockAssessment:
        return cls(
            increments=d.get("increments", []),
            decrements=d.get("decrements", []),
            triggered=d.get("triggered", []),
            surface_now=d.get("surface_now", False),
        )


# ---------------------------------------------------------------------------
# State types
# ---------------------------------------------------------------------------

@dataclass
class CharacterState:
    """
    Current emotional and physical state for Senna.
    Injected near generation point for high influence on tone.
    """
    mood: Mood = Mood.FOCUSED
    energy: EnergyLevel = EnergyLevel.NORMAL
    research_excitement: str = "normal"   # low / normal / high
    tension_with_garion: str = "none"     # none / mild / moderate / high

    def to_dict(self) -> dict:
        return {
            "mood": self.mood.value,
            "energy": self.energy.value,
            "research_excitement": self.research_excitement,
            "tension_with_garion": self.tension_with_garion,
        }

    def to_prompt_fragment(self) -> str:
        """Human-readable fragment for injection into context."""
        lines = [
            f"Senna's current mood: {self.mood.value}",
            f"Energy: {self.energy.value}",
            f"Research excitement: {self.research_excitement}",
        ]
        if self.tension_with_garion != "none":
            lines.append(f"Tension with Garion: {self.tension_with_garion}")
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, d: dict) -> CharacterState:
        return cls(
            mood=Mood(d.get("mood", "focused")),
            energy=EnergyLevel(d.get("energy", "normal")),
            research_excitement=d.get("research_excitement", "normal"),
            tension_with_garion=d.get("tension_with_garion", "none"),
        )


@dataclass
class ResearchState:
    """Tracks Senna's current research progress."""
    project_name: str = "Adaptive Spell Framework"
    progress: int = 0           # 0-100
    current_obstacle: Optional[str] = None
    recent_breakthrough: Optional[str] = None
    materials_needed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "progress": self.progress,
            "current_obstacle": self.current_obstacle,
            "recent_breakthrough": self.recent_breakthrough,
            "materials_needed": self.materials_needed,
        }

    def to_prompt_fragment(self) -> str:
        lines = [f"Research: {self.project_name} — {self.progress}% complete"]
        if self.current_obstacle:
            lines.append(f"Current obstacle: {self.current_obstacle}")
        if self.recent_breakthrough:
            lines.append(f"Recent breakthrough: {self.recent_breakthrough}")
        if self.materials_needed:
            lines.append(f"Still needs: {', '.join(self.materials_needed)}")
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, d: dict) -> ResearchState:
        return cls(
            project_name=d.get("project_name", "Adaptive Spell Framework"),
            progress=d.get("progress", 0),
            current_obstacle=d.get("current_obstacle"),
            recent_breakthrough=d.get("recent_breakthrough"),
            materials_needed=d.get("materials_needed", []),
        )


@dataclass
class RelationshipState:
    """Tracks the Garion/Senna relationship arc."""
    trust: int = 80             # 0-100
    tension: int = 0            # 0-100
    history_depth: int = 20     # grows over sessions
    last_significant_moment: Optional[str] = None
    unspoken_things: list[str] = field(default_factory=list)  # feeds relationship clock

    def to_dict(self) -> dict:
        return {
            "trust": self.trust,
            "tension": self.tension,
            "history_depth": self.history_depth,
            "last_significant_moment": self.last_significant_moment,
            "unspoken_things": self.unspoken_things,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RelationshipState:
        return cls(
            trust=d.get("trust", 80),
            tension=d.get("tension", 0),
            history_depth=d.get("history_depth", 20),
            last_significant_moment=d.get("last_significant_moment"),
            unspoken_things=d.get("unspoken_things", []),
        )


@dataclass
class WorldState:
    """Current state of the world and active NPCs."""
    current_location: str = "Vethara"
    active_npc_states: dict[str, dict] = field(default_factory=dict)
    world_events: list[str] = field(default_factory=list)  # ambient events queue

    def to_dict(self) -> dict:
        return {
            "current_location": self.current_location,
            "active_npc_states": self.active_npc_states,
            "world_events": self.world_events,
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorldState:
        return cls(
            current_location=d.get("current_location", "Vethara"),
            active_npc_states=d.get("active_npc_states", {}),
            world_events=d.get("world_events", []),
        )


# ---------------------------------------------------------------------------
# Injection context — what gets built and sent to the model
# ---------------------------------------------------------------------------

@dataclass
class InjectionContext:
    """
    The assembled context that gets injected into the prompt.
    Built by the Injector component from all other component outputs.
    """
    retrieved_memories: list[RetrievedMemory] = field(default_factory=list)
    character_state: Optional[CharacterState] = None
    research_state: Optional[ResearchState] = None
    relationship_state: Optional[RelationshipState] = None
    pending_clock_effect: Optional[str] = None   # surfaced clock trigger
    session_tone: Optional[str] = None           # optional tone note

    def has_content(self) -> bool:
        return any([
            self.retrieved_memories,
            self.character_state,
            self.research_state,
            self.pending_clock_effect,
            self.session_tone,
        ])

    def to_dict(self) -> dict:
        return {
            "retrieved_memories": [m.to_dict() for m in self.retrieved_memories],
            "character_state": self.character_state.to_dict() if self.character_state else None,
            "research_state": self.research_state.to_dict() if self.research_state else None,
            "relationship_state": self.relationship_state.to_dict() if self.relationship_state else None,
            "pending_clock_effect": self.pending_clock_effect,
            "session_tone": self.session_tone,
        }


# ---------------------------------------------------------------------------
# Evaluation result — used by tier 2 inference tests
# ---------------------------------------------------------------------------

@dataclass
class EvaluationResult:
    """Structured output from an inference quality check."""
    passed: bool
    criteria_results: dict[str, bool] = field(default_factory=dict)
    notes: str = ""
    score: Optional[str] = None   # e.g. "2/3" for multi-run checks

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "criteria_results": self.criteria_results,
            "notes": self.notes,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, d: dict) -> EvaluationResult:
        return cls(
            passed=d["passed"],
            criteria_results=d.get("criteria_results", {}),
            notes=d.get("notes", ""),
            score=d.get("score"),
        )