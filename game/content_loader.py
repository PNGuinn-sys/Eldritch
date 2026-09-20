"""
Loads and validates a scenario (an "adventure") from its data files.

A scenario lives in data/<name>/ as a handful of YAML files:
  manifest.yaml - title, description, starting room, intro text
  rooms.yaml     - room templates (description variants, exits)
  items.yaml      - item templates (placement pools, sanity effects)
  events.yaml       - random one-time event templates

Nothing in here is game *logic* - it's purely reading and sanity-checking
the shape of hand-authored content, so a mistake in a data file shows up
as a clear error message at startup instead of a crash mid-playthrough.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from game.entities import DEFAULT_CHANCE_BY_TIER, DREAD_THRESHOLD

VALID_TIER_KEYS = {"lucid", "uneasy", "fraying", "broken"}

# A universal artifact, present in every scenario whether or not its
# items.yaml defines one. If a scenario DOES define its own "necronomicon"
# item (for tailored flavor text), that version is used instead - only
# the mechanic (see main.py's "use" handling) is engine-enforced, not
# the prose. valid_rooms is left empty here and filled in per-scenario
# at load time, since the shared definition can't know a scenario's
# room ids in advance.
SHARED_NECRONOMICON = {
    "name": "necronomicon",
    "description": (
        "A heavy book bound in something that was never leather. You can "
        "tell, just holding it, that skimming it is one thing and actually "
        "reading it is another - and that the second one isn't a decision "
        "you get to take back. Reading it costs roughly half of whatever "
        "sanity you have left, leaves you unable to recover any more of it "
        "for the rest of this attempt, and grants the equivalent of two "
        "clues in return. There's no reading it partway."
    ),
    "on_take_sanity": -10,
    "on_take_text": (
        "It falls open on its own, as if it's been waiting. You close it "
        "again before you can read anything you'd remember - for now."
    ),
}


class ScenarioError(Exception):
    """Raised when a scenario's data files are missing, malformed, or
    internally inconsistent."""


@dataclass
class Scenario:
    name: str
    title: str
    description: str
    start_room: str
    rooms: Dict[str, dict]
    items: Dict[str, dict]
    events: List[dict]
    intro: str = ""
    max_sanity: int = 100
    clues_required: Optional[int] = None
    threat: dict = field(default_factory=lambda: {
        "threshold": DREAD_THRESHOLD,
        "chance_by_tier": dict(DEFAULT_CHANCE_BY_TIER),
        "manifest_text": None,
        "caught_text": None,
        "evade_text": None,
        "hide_text": None,
    })
    sanity_tier_thresholds: Optional[dict] = None
    win_text: Optional[str] = None
    broken_text: Optional[str] = None


def load_scenario(data_dir: Path) -> Scenario:
    """Load and validate a scenario's data files from `data_dir`
    (e.g. data/manor). Raises ScenarioError on any problem."""
    manifest = _load_yaml(data_dir / "manifest.yaml") or {}
    rooms = _load_yaml(data_dir / "rooms.yaml") or {}
    items = _load_yaml(data_dir / "items.yaml") or {}
    events = _load_yaml(data_dir / "events.yaml") or []

    if "start_room" not in manifest:
        raise ScenarioError(
            f"{data_dir / 'manifest.yaml'}: missing required field 'start_room'"
        )

    if "necronomicon" not in items:
        items = dict(items)
        items["necronomicon"] = dict(SHARED_NECRONOMICON, valid_rooms=list(rooms.keys()))

    manifest_threat = manifest.get("threat") or {}
    threat = {
        "threshold": manifest_threat.get("threshold", DREAD_THRESHOLD),
        "chance_by_tier": {**DEFAULT_CHANCE_BY_TIER, **(manifest_threat.get("chance_by_tier") or {})},
        "manifest_text": manifest_threat.get("manifest_text"),
        "caught_text": manifest_threat.get("caught_text"),
        "evade_text": manifest_threat.get("evade_text"),
        "hide_text": manifest_threat.get("hide_text"),
    }

    scenario = Scenario(
        name=data_dir.name,
        title=manifest.get("title", data_dir.name),
        description=manifest.get("description", ""),
        intro=manifest.get("intro", ""),
        start_room=manifest["start_room"],
        rooms=rooms,
        items=items,
        events=events,
        max_sanity=manifest.get("max_sanity", 100),
        clues_required=manifest.get("clues_required"),
        threat=threat,
        sanity_tier_thresholds=manifest.get("sanity_tier_thresholds"),
        win_text=manifest.get("win_text"),
        broken_text=manifest.get("broken_text"),
    )

    errors = validate_scenario(scenario)
    if errors:
        formatted = "\n".join(f"  - {e}" for e in errors)
        raise ScenarioError(
            f"Scenario '{scenario.name}' failed validation:\n{formatted}"
        )

    return scenario


def discover_scenarios(data_dir: Path) -> List[dict]:
    """Return [{"id", "title", "description"}, ...] for every playable
    scenario folder under data_dir, sorted by folder name. Folders
    starting with "_" (like _template) are treated as internal/
    reference-only and excluded - they're still loadable directly via
    --scenario, just hidden from discovery. A folder only needs the
    four required files and a readable manifest to appear here; full
    validation happens when a scenario is actually loaded and played."""
    required_files = ("manifest.yaml", "rooms.yaml", "items.yaml", "events.yaml")
    scenarios = []
    if not data_dir.exists():
        return scenarios

    for entry in sorted(data_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        if not all((entry / f).exists() for f in required_files):
            continue

        title, description = entry.name, ""
        try:
            manifest = _load_yaml(entry / "manifest.yaml") or {}
            title = manifest.get("title", entry.name)
            description = manifest.get("description", "")
        except ScenarioError:
            pass  # fall back to the folder name rather than hiding a broken-but-present scenario

        scenarios.append({"id": entry.name, "title": title, "description": description})

    return scenarios


def _load_yaml(path: Path):
    if not path.exists():
        raise ScenarioError(f"Missing required file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        try:
            return yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ScenarioError(f"{path}: invalid YAML - {e}") from e


def validate_scenario(scenario: Scenario) -> List[str]:
    """Return a list of human-readable problems with the scenario's
    content. An empty list means the scenario is valid."""
    errors: List[str] = []
    room_ids = set(scenario.rooms.keys())

    if scenario.start_room not in room_ids:
        errors.append(f"start_room '{scenario.start_room}' is not a defined room")

    for room_id, room in scenario.rooms.items():
        if not room.get("description_variants"):
            errors.append(f"room '{room_id}' has no description_variants")

        for direction, exit_info in room.get("exits", {}).items():
            target = exit_info.get("target")
            requires_all_clues = exit_info.get("requires_all_clues")

            if target is None and not requires_all_clues:
                errors.append(
                    f"room '{room_id}' exit '{direction}' has no target "
                    f"(and isn't a requires_all_clues exit)"
                )
            if target is not None and target not in room_ids:
                errors.append(
                    f"room '{room_id}' exit '{direction}' targets "
                    f"unknown room '{target}'"
                )

            unlock_item = exit_info.get("unlock_item")
            if exit_info.get("locked") and not unlock_item and not requires_all_clues:
                errors.append(
                    f"room '{room_id}' exit '{direction}' is locked but has "
                    f"no unlock_item"
                )
            if unlock_item and unlock_item not in scenario.items:
                errors.append(
                    f"room '{room_id}' exit '{direction}' unlock_item "
                    f"'{unlock_item}' is not a defined item"
                )

    for item_id, item in scenario.items.items():
        if not item.get("valid_rooms"):
            errors.append(f"item '{item_id}' has no valid_rooms")
        for room_id in item.get("valid_rooms", []):
            if room_id not in room_ids:
                errors.append(
                    f"item '{item_id}' valid_rooms references unknown "
                    f"room '{room_id}'"
                )
        if item.get("is_clue") and item.get("on_use_sanity"):
            errors.append(
                f"item '{item_id}' is both is_clue and on_use_sanity - using "
                f"it consumes it, which would silently remove a required clue"
            )
        if "on_use_sanity" in item and item["on_use_sanity"] <= 0:
            errors.append(
                f"item '{item_id}' on_use_sanity should be positive "
                f"(it's meant to restore sanity, not drain it)"
            )

    for event in scenario.events:
        event_id = event.get("id", "<missing id>")
        if "id" not in event:
            errors.append("an event is missing its 'id' field")
        for room_id in event.get("rooms", []):
            if room_id not in room_ids:
                errors.append(
                    f"event '{event_id}' references unknown room '{room_id}'"
                )

    has_clue = any(item.get("is_clue") for item in scenario.items.values())
    has_win_exit = any(
        exit_info.get("requires_all_clues")
        for room in scenario.rooms.values()
        for exit_info in room.get("exits", {}).values()
    )
    if has_clue and not has_win_exit:
        errors.append("items are marked is_clue, but no exit has requires_all_clues")
    if has_win_exit and not has_clue:
        errors.append("an exit has requires_all_clues, but no item is marked is_clue")

    total_clues = sum(1 for item in scenario.items.values() if item.get("is_clue"))
    if scenario.clues_required is not None:
        if scenario.clues_required <= 0:
            errors.append("clues_required must be a positive integer")
        elif scenario.clues_required > total_clues:
            errors.append(
                f"clues_required ({scenario.clues_required}) is greater than "
                f"the total number of is_clue items ({total_clues})"
            )

    if scenario.max_sanity is not None and scenario.max_sanity <= 0:
        errors.append(f"max_sanity must be a positive integer, got {scenario.max_sanity}")

    for room_id, room in scenario.rooms.items():
        rest_amount = room.get("rest_amount")
        if rest_amount is not None and rest_amount <= 0:
            errors.append(f"room '{room_id}' has a non-positive rest_amount")

        risk_multiplier = room.get("risk_multiplier")
        if risk_multiplier is not None and risk_multiplier <= 0:
            errors.append(f"room '{room_id}' has a non-positive risk_multiplier")

    threat = scenario.threat or {}
    if threat.get("threshold", DREAD_THRESHOLD) < 1:
        errors.append(f"threat.threshold must be at least 1, got {threat.get('threshold')}")
    for key, value in (threat.get("chance_by_tier") or {}).items():
        if key not in VALID_TIER_KEYS:
            errors.append(
                f"threat.chance_by_tier has unknown tier key '{key}' "
                f"(expected one of {sorted(VALID_TIER_KEYS)})"
            )
        elif not (0 <= value <= 1):
            errors.append(f"threat.chance_by_tier['{key}'] must be between 0 and 1, got {value}")

    if scenario.sanity_tier_thresholds is not None:
        tiers = scenario.sanity_tier_thresholds
        for key in tiers:
            if key not in ("lucid", "uneasy", "fraying"):
                errors.append(
                    f"sanity_tier_thresholds has unknown key '{key}' "
                    f"(expected one of ['lucid', 'uneasy', 'fraying'] - "
                    f"'broken' is always the implicit floor)"
                )
        lucid = tiers.get("lucid", 0.80)
        uneasy = tiers.get("uneasy", 0.50)
        fraying = tiers.get("fraying", 0.25)
        if not (0 < fraying < uneasy < lucid <= 1):
            errors.append(
                "sanity_tier_thresholds must satisfy 0 < fraying < uneasy < "
                f"lucid <= 1, got fraying={fraying}, uneasy={uneasy}, lucid={lucid}"
            )

    return errors
