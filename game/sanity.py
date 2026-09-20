"""
Sanity system for Eldritch.

Sanity isn't just a number on a status screen - as it drops, the game's
own narration becomes unreliable. This module defines the sanity tiers
and the text distortion applied at each level.

This is a first pass focused on narration. Gameplay-altering effects
(false exits, misdirected movement, etc.) will build on this once we
have real rooms to design around.
"""

from enum import Enum
import random


class SanityTier(Enum):
    LUCID = "Lucid"
    UNEASY = "Uneasy"
    FRAYING = "Fraying"
    BROKEN = "Broken"


_DEFAULT_TIER_PERCENT_THRESHOLDS = (
    (0.80, SanityTier.LUCID),
    (0.50, SanityTier.UNEASY),
    (0.25, SanityTier.FRAYING),
    (0.0, SanityTier.BROKEN),
)

_INTRUSIVE_THOUGHTS = [
    "(That wasn't there a moment ago. Was it?)",
    "(You've stood in this exact spot before. You're certain of it.)",
    "(Something is keeping count of your footsteps.)",
    "(The proportions of this place are wrong, and getting wronger.)",
    "(You no longer remember which way you came from.)",
]


def thresholds_from_dict(overrides):
    """Build a (percent, SanityTier) tuple table from a scenario's
    optional sanity_tier_thresholds dict (keys: lucid/uneasy/fraying -
    broken is always the implicit 0.0 floor). Returns None if no
    overrides are given, so callers fall back to the engine default."""
    if not overrides:
        return None
    return (
        (overrides.get("lucid", 0.80), SanityTier.LUCID),
        (overrides.get("uneasy", 0.50), SanityTier.UNEASY),
        (overrides.get("fraying", 0.25), SanityTier.FRAYING),
        (0.0, SanityTier.BROKEN),
    )


def tier_for(sanity: int, max_sanity: int = 100, thresholds=None) -> SanityTier:
    """Return the SanityTier for a given sanity value, as a percentage of
    max_sanity - so tiers scale correctly whatever a scenario's sanity
    pool is, rather than assuming it's always out of 100. `thresholds`
    optionally overrides the default 80/50/25% breakpoints (see
    thresholds_from_dict)."""
    if max_sanity <= 0:
        return SanityTier.BROKEN
    percent = sanity / max_sanity
    table = thresholds if thresholds is not None else _DEFAULT_TIER_PERCENT_THRESHOLDS
    for threshold, tier in table:
        if percent >= threshold:
            return tier
    return SanityTier.BROKEN


def distort(text: str, sanity: int, rng: random.Random = random, max_sanity: int = 100,
            thresholds=None) -> str:
    """Apply sanity-based narration distortion to a piece of room text."""
    tier = tier_for(sanity, max_sanity, thresholds)

    if tier is SanityTier.LUCID:
        return text

    if tier is SanityTier.UNEASY:
        if rng.random() < 0.3:
            text = f"{text} {rng.choice(_INTRUSIVE_THOUGHTS)}"
        return text

    if tier is SanityTier.FRAYING:
        if rng.random() < 0.6:
            text = f"{text} {rng.choice(_INTRUSIVE_THOUGHTS)}"
        if rng.random() < 0.35:
            text = _stutter(text, rng)
        return text

    # BROKEN
    text = f"{text} {rng.choice(_INTRUSIVE_THOUGHTS)}"
    if rng.random() < 0.5:
        text = _stutter(text, rng)
    if rng.random() < 0.4:
        text += " ...or is that not quite what you saw?"
    return text


def _stutter(text: str, rng: random.Random) -> str:
    """Repeat a random word mid-sentence, as if the narrator lost their place."""
    words = text.split(" ")
    if len(words) < 5:
        return text
    idx = rng.randrange(1, len(words) - 1)
    words.insert(idx, words[idx])
    return " ".join(words)
