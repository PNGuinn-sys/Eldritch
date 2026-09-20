"""
Automatic difficulty scaling for sanity costs and presence dread.

Both existing scenarios (the manor, Hollow Tide) were hand-tuned and
actually playtested at a specific size: 7 rooms, and 8 pieces of
content that cost sanity (items with on_take_sanity + events with
sanity_effect). Without scaling, a bigger scenario built the same way
- more clues, more events, more rooms - would drain sanity and summon
the presence far more often than intended, since costs are additive:
more content pieces means more total sanity lost, and a bigger map
means more turns for dread to accumulate across.

Rather than requiring every scenario author to hand-rebalance every
item and event as content grows, both dread frequency and per-item
sanity costs scale automatically relative to that baseline, so a
playthrough feels similarly paced regardless of scenario size. A
scenario can still override either scale explicitly in manifest.yaml
(dread_scale / sanity_scale) if it's meant to feel unusually harsh or
lenient regardless of its size.
"""

BASELINE_ROOM_COUNT = 7
BASELINE_SANITY_UNITS = 8

MIN_SCALE = 0.35
MAX_SCALE = 2.5


def _clamp(value: float) -> float:
    return max(MIN_SCALE, min(MAX_SCALE, value))


def compute_dread_scale(room_count: int) -> float:
    """Multiplier for the presence's per-turn manifestation chance. A
    bigger map means more turns spent exploring it, so the per-turn
    chance scales down to keep the *number* of manifestations across a
    full playthrough roughly similar."""
    return _clamp(BASELINE_ROOM_COUNT / max(1, room_count))


def compute_sanity_scale(sanity_affecting_unit_count: int) -> float:
    """Multiplier applied to every authored on_take_sanity / sanity_effect
    value. More clues and events means more chances to lose sanity, so
    each individual cost scales down to keep the *total* possible drain
    across a full playthrough roughly similar."""
    return _clamp(BASELINE_SANITY_UNITS / max(1, sanity_affecting_unit_count))


def count_sanity_affecting_units(items: dict, events: list) -> int:
    """How many pieces of content in a scenario can cost sanity at all -
    the denominator compute_sanity_scale scales against."""
    item_units = sum(1 for template in items.values() if template.get("on_take_sanity"))
    event_units = sum(1 for event in events if event.get("sanity_effect"))
    return item_units + event_units
