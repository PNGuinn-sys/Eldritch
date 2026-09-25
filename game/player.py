"""
Player state for Eldritch: location, sanity, and inventory.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set

from game.sanity import tier_for, SanityTier

MIN_SANITY = 0
DEFAULT_MAX_SANITY = 100


@dataclass
class Player:
    location: str
    sanity: int = DEFAULT_MAX_SANITY
    max_sanity: int = DEFAULT_MAX_SANITY
    tier_thresholds: object = None  # Optional[tuple] - custom (percent, SanityTier) pairs
    inventory: List[str] = field(default_factory=list)
    visited: Set[str] = field(default_factory=set)
    dread: int = 0
    presence_active: bool = False
    bonus_clues: int = 0
    necronomicon_read: bool = False
    regeneration_disabled: bool = False
    chapter: Optional[str] = None  # id of the chapter last announced, if the scenario has any
    threat_explained: bool = False  # has the flee-or-hide instruction been shown this run?

    @property
    def sanity_tier(self) -> SanityTier:
        return tier_for(self.sanity, self.max_sanity, self.tier_thresholds)

    def adjust_sanity(self, amount: int) -> int:
        """Change sanity by `amount` (positive or negative), clamped to
        [MIN_SANITY, max_sanity]. Returns the new sanity value."""
        self.sanity = max(MIN_SANITY, min(self.max_sanity, self.sanity + amount))
        return self.sanity

    def add_item(self, item_id: str) -> None:
        self.inventory.append(item_id)

    def remove_item(self, item_id: str) -> bool:
        if item_id in self.inventory:
            self.inventory.remove(item_id)
            return True
        return False

    def has_item(self, item_id: str) -> bool:
        return item_id in self.inventory
