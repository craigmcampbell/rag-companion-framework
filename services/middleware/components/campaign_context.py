"""
campaign_context.py — Campaign-specific configuration for the middleware.

CampaignContext holds everything that varies between campaigns:
- Character names, roles, and relationships
- Setting description
- Any framing the AI components need to do their job correctly

The framework components (extractor, assessor, state manager) are all
generic. They receive a CampaignContext and use it to build prompts.
This means adding a new campaign is a new YAML file, not a code change.

Loading:
    ctx = CampaignContext.from_yaml("campaigns/senna.yml")
    ctx = CampaignContext.from_yaml("campaigns/starforged.yml")
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class CharacterConfig:
    """Configuration for a single character in the campaign."""
    name: str
    role: str                           # Brief role description
    description: str = ""              # Longer description for prompt context


@dataclass
class CampaignContext:
    """
    All campaign-specific context the middleware needs.

    Injected into extractors, assessors, and state managers so the
    framework layer stays generic and campaigns stay in config files.
    """
    # Campaign identity
    campaign_id: str                    # Matches collection name: senna_memory
    campaign_name: str                  # Human readable: "Senna Campaign"
    genre: str                         # "fantasy" | "sci-fi" | "horror" etc.

    # Characters
    user_character: CharacterConfig     # The player character (Garion, Brennan...)
    companion_character: CharacterConfig  # The AI companion (Senna, Sable...)

    # Relationship framing
    relationship: str                  # One sentence describing their dynamic
    setting: str                       # Brief world/setting description

    # Optional additional context for prompts
    extra_context: str = ""            # Anything else the AI should know

    @property
    def prompt_preamble(self) -> str:
        """
        Compact context block injected into all AI prompts.
        Generic enough to work for any campaign.
        """
        lines = [
            f"Campaign: {self.campaign_name} ({self.genre})",
            f"Setting: {self.setting}",
            f"{self.user_character.name} ({self.user_character.role})",
            f"{self.companion_character.name} ({self.companion_character.role})",
            f"Relationship: {self.relationship}",
        ]
        if self.extra_context:
            lines.append(self.extra_context)
        return "\n".join(lines)

    @classmethod
    def from_yaml(cls, path: str | Path) -> CampaignContext:
        """Load a CampaignContext from a YAML config file."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Campaign config not found: {p}")

        with open(p) as f:
            data = yaml.safe_load(f)

        return cls(
            campaign_id=data["campaign_id"],
            campaign_name=data["campaign_name"],
            genre=data["genre"],
            user_character=CharacterConfig(**data["user_character"]),
            companion_character=CharacterConfig(**data["companion_character"]),
            relationship=data["relationship"],
            setting=data["setting"],
            extra_context=data.get("extra_context", ""),
        )

    def to_dict(self) -> dict:
        return {
            "campaign_id": self.campaign_id,
            "campaign_name": self.campaign_name,
            "genre": self.genre,
            "user_character": {
                "name": self.user_character.name,
                "role": self.user_character.role,
                "description": self.user_character.description,
            },
            "companion_character": {
                "name": self.companion_character.name,
                "role": self.companion_character.role,
                "description": self.companion_character.description,
            },
            "relationship": self.relationship,
            "setting": self.setting,
            "extra_context": self.extra_context,
        }