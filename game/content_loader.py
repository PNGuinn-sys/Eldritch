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

from game.balance import compute_dread_scale, compute_sanity_scale, count_sanity_affecting_units
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
    # Resolved at load time (manifest override, else auto-computed from
    # scenario size - see game/balance.py). 1.0 means "as authored".
    dread_scale: float = 1.0
    sanity_scale: float = 1.0
    # Optional story structure: {chapter_id: {"title", "intro", "threat"}}.
    # chapter_threats holds each chapter's threat with its overrides already
    # merged over the scenario-wide one (see threat_for).
    chapters: dict = field(default_factory=dict)
    chapter_threats: dict = field(default_factory=dict)

    def threat_for(self, room: dict) -> dict:
        """The threat config in force in `room` - its chapter's merged
        override if it has one, else the scenario-wide threat."""
        return self.chapter_threats.get(room.get("chapter"), self.threat)


def _scale_amount(value, scale: float):
    """Scale an authored sanity amount, keeping its sign and never letting
    a nonzero cost round away to nothing."""
    scaled = round(value * scale)
    if scaled == 0 and value != 0:
        return 1 if value > 0 else -1
    return scaled


def _apply_sanity_scale(items: dict, events: list, scale: float):
    """Return (items, events) with every on_take_sanity / sanity_effect
    scaled. Copies - the loaded YAML dicts are left untouched. Restorative
    on_use_sanity values are deliberately NOT scaled: scaling costs down
    while shrinking recovery too would just be a second difficulty knob."""
    if scale == 1.0:
        return items, events
    new_items = {}
    for item_id, template in items.items():
        template = dict(template)
        if template.get("on_take_sanity"):
            template["on_take_sanity"] = _scale_amount(template["on_take_sanity"], scale)
        new_items[item_id] = template
    new_events = []
    for event in events:
        event = dict(event)
        if event.get("sanity_effect"):
            event["sanity_effect"] = _scale_amount(event["sanity_effect"], scale)
        new_events.append(event)
    return new_items, new_events


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

    chapters = manifest.get("chapters") or {}
    if not isinstance(chapters, dict):
        raise ScenarioError(
            f"{data_dir / 'manifest.yaml'}: 'chapters' must be a mapping of "
            f"chapter id to its title/intro/threat"
        )
    chapter_threats = {}
    for chapter_id, chapter in chapters.items():
        override = (chapter or {}).get("threat") or {}
        chapter_threats[chapter_id] = {
            "threshold": override.get("threshold", threat["threshold"]),
            "chance_by_tier": {**threat["chance_by_tier"], **(override.get("chance_by_tier") or {})},
            **{k: override.get(k) or threat[k]
               for k in ("manifest_text", "caught_text", "evade_text", "hide_text")},
        }

    dread_scale = manifest.get("dread_scale")
    if dread_scale is None:
        dread_scale = compute_dread_scale(len(rooms))
    sanity_scale = manifest.get("sanity_scale")
    if sanity_scale is None:
        sanity_scale = compute_sanity_scale(count_sanity_affecting_units(items, events))
    items, events = _apply_sanity_scale(items, events, sanity_scale)

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
        dread_scale=dread_scale,
        sanity_scale=sanity_scale,
        chapters=chapters,
        chapter_threats=chapter_threats,
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


def _validate_threat(threat: dict, label: str) -> List[str]:
    """Problems in a threat block (the scenario-wide one, or a chapter's
    partial override of it)."""
    errors: List[str] = []
    if threat.get("threshold", DREAD_THRESHOLD) < 1:
        errors.append(f"{label}.threshold must be at least 1, got {threat.get('threshold')}")
    for key, value in (threat.get("chance_by_tier") or {}).items():
        if key not in VALID_TIER_KEYS:
            errors.append(
                f"{label}.chance_by_tier has unknown tier key '{key}' "
                f"(expected one of {sorted(VALID_TIER_KEYS)})"
            )
        elif not (0 <= value <= 1):
            errors.append(f"{label}.chance_by_tier['{key}'] must be between 0 and 1, got {value}")
    return errors


def _validate_finale(room_id: str, direction: str, finale, scenario: Scenario) -> List[str]:
    """Problems in an exit's `finale` list: tiered endings picked by clue
    count, evaluated top to bottom, the last entry being the fallback."""
    where = f"room '{room_id}' exit '{direction}' finale"
    if not isinstance(finale, list) or not finale:
        return [f"{where} must be a non-empty list of endings"]
    errors: List[str] = []
    total = sum(1 for i in scenario.items.values() if i.get("is_clue"))
    previous = None
    for n, entry in enumerate(finale, start=1):
        if not isinstance(entry, dict) or not entry.get("text"):
            errors.append(f"{where} entry {n} needs a 'text'")
            continue
        if entry.get("result") not in ("win", "lose"):
            errors.append(f"{where} entry {n} result must be 'win' or 'lose', got {entry.get('result')!r}")
        minimum = entry.get("min_clues")
        if minimum is None:
            if n != len(finale):
                errors.append(f"{where} entry {n} has no min_clues, so every entry after it is unreachable")
            continue
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum <= 0:
            errors.append(f"{where} entry {n} min_clues must be a positive integer, got {minimum!r}")
            continue
        if minimum > total:
            errors.append(f"{where} entry {n} min_clues ({minimum}) is greater than the total is_clue items ({total})")
        if previous is not None and minimum >= previous:
            errors.append(f"{where} entries must go from highest min_clues to lowest (entry {n} is {minimum} after {previous})")
        previous = minimum
    if isinstance(finale[-1], dict) and finale[-1].get("min_clues") is not None:
        errors.append(f"{where} needs a last entry with no min_clues, as the fallback ending")
    return errors


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
            finale = exit_info.get("finale")

            if target is None and not requires_all_clues and not finale:
                errors.append(
                    f"room '{room_id}' exit '{direction}' has no target "
                    f"(and isn't a requires_all_clues or finale exit)"
                )
            if finale:
                errors.extend(_validate_finale(room_id, direction, finale, scenario))
            if "requires_clues" in exit_info:
                needed = exit_info["requires_clues"]
                total = sum(1 for i in scenario.items.values() if i.get("is_clue"))
                if isinstance(needed, bool) or not isinstance(needed, int) or needed <= 0:
                    errors.append(
                        f"room '{room_id}' exit '{direction}' requires_clues must be a "
                        f"positive integer, got {needed!r}"
                    )
                elif needed > total:
                    errors.append(
                        f"room '{room_id}' exit '{direction}' requires_clues ({needed}) is "
                        f"greater than the total number of is_clue items ({total})"
                    )
                if target is None:
                    errors.append(
                        f"room '{room_id}' exit '{direction}' has requires_clues but no target"
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
        exit_info.get("requires_all_clues") or exit_info.get("finale")
        for room in scenario.rooms.values()
        for exit_info in room.get("exits", {}).values()
    )
    if has_clue and not has_win_exit:
        errors.append("items are marked is_clue, but no exit has requires_all_clues or a finale")
    if has_win_exit and not has_clue:
        errors.append("an exit has requires_all_clues or a finale, but no item is marked is_clue")

    total_clues = sum(1 for item in scenario.items.values() if item.get("is_clue"))
    if scenario.clues_required is not None:
        if scenario.clues_required <= 0:
            errors.append("clues_required must be a positive integer")
        elif scenario.clues_required > total_clues:
            errors.append(
                f"clues_required ({scenario.clues_required}) is greater than "
                f"the total number of is_clue items ({total_clues})"
            )

    for key in ("dread_scale", "sanity_scale"):
        value = getattr(scenario, key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            errors.append(f"{key} must be a positive number, got {value!r}")

    if scenario.max_sanity is not None and scenario.max_sanity <= 0:
        errors.append(f"max_sanity must be a positive integer, got {scenario.max_sanity}")

    for room_id, room in scenario.rooms.items():
        rest_amount = room.get("rest_amount")
        if rest_amount is not None and rest_amount <= 0:
            errors.append(f"room '{room_id}' has a non-positive rest_amount")

        risk_multiplier = room.get("risk_multiplier")
        if risk_multiplier is not None and risk_multiplier <= 0:
            errors.append(f"room '{room_id}' has a non-positive risk_multiplier")

    errors.extend(_validate_threat(scenario.threat or {}, "threat"))

    for chapter_id, chapter in scenario.chapters.items():
        if not isinstance(chapter, dict) or not chapter.get("title"):
            errors.append(f"chapter '{chapter_id}' needs a title")
            continue
        errors.extend(_validate_threat(chapter.get("threat") or {}, f"chapter '{chapter_id}' threat"))
    if scenario.chapters:
        for room_id, room in scenario.rooms.items():
            chapter_id = room.get("chapter")
            if chapter_id is not None and chapter_id not in scenario.chapters:
                errors.append(f"room '{room_id}' is in unknown chapter '{chapter_id}'")
    else:
        for room_id, room in scenario.rooms.items():
            if room.get("chapter") is not None:
                errors.append(f"room '{room_id}' has a chapter but the manifest defines no chapters")

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
