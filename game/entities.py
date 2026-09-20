"""
The presence - an unseen threat stalking the world.

This isn't a monster to fight; it's built entirely around avoidance.
Dread quietly accumulates while the player explores, building faster
the further their sanity has slipped (and faster still in rooms a
scenario marks as riskier - a public street, say). Once dread crosses
a threshold, the threat manifests in the player's current room, and
their very next action has to be an evasion (fleeing to another room,
or hiding) or they're caught.

Every scenario shares this same underlying mechanic, but a scenario's
manifest.yaml can retune its pacing (threshold, chance_by_tier) and
reskin its flavor text entirely - so "the presence" in one scenario and
"the shambler" in another can feel like completely different threats
even though the code beneath them is identical.
"""

DREAD_THRESHOLD = 3

DEFAULT_CHANCE_BY_TIER = {
    "lucid": 0.12,
    "uneasy": 0.22,
    "fraying": 0.35,
    "broken": 0.50,
}

DEFAULT_THREAT_CONFIG = {
    "threshold": DREAD_THRESHOLD,
    "chance_by_tier": DEFAULT_CHANCE_BY_TIER,
}


def advance_dread(player, rng, threat_config=None, risk_multiplier: float = 1.0) -> bool:
    """Roll for the threat's dread to build by one step, based on the
    player's current sanity tier and the current room's risk_multiplier
    (some rooms - a public street, say - are riskier than others).
    Returns True if it just manifested in the player's room this turn
    (setting player.presence_active). `threat_config` defaults to the
    engine's built-in pacing if a scenario doesn't override it."""
    if player.presence_active:
        return False

    config = threat_config or DEFAULT_THREAT_CONFIG
    chance_by_tier = config.get("chance_by_tier") or DEFAULT_CHANCE_BY_TIER
    tier_key = player.sanity_tier.name.lower()
    base_chance = chance_by_tier.get(tier_key, DEFAULT_CHANCE_BY_TIER[tier_key])

    chance = min(1.0, base_chance * risk_multiplier)
    if rng.random() < chance:
        player.dread += 1

    threshold = config.get("threshold", DREAD_THRESHOLD)
    if player.dread >= threshold:
        player.presence_active = True
        return True

    return False


def resolve_evasion(player) -> None:
    """Call once the player successfully evades (flees or hides)."""
    player.presence_active = False
    player.dread = 0
