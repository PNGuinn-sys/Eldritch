"""
Save / load for Eldritch.

A save stores only what *changes* during a playthrough - the player, where
every item currently is, which doors have been unlocked, which one-shot
events have fired, each room's chosen description variant, and the RNG
state (so a loaded game keeps rolling the same dice). Static content (room
names, exits, item text) is never saved: it's re-read from the scenario's
data files, so editing prose doesn't invalidate saves.

Structural edits (adding/removing rooms, items or events) do invalidate
them, since a saved item location might no longer make sense. A content
fingerprint of those ids catches that and refuses the load with a clear
message rather than corrupting the game.
"""

import dataclasses
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List

SAVE_VERSION = 1
DEFAULT_SLOT = "quicksave"
_SLOT_RE = re.compile(r"^[a-z0-9_-]{1,32}$")

# Player fields that are derived from the scenario at startup, not state.
_PLAYER_DERIVED_FIELDS = {"tier_thresholds"}


class SaveError(Exception):
    """A save couldn't be written, read, or applied to this scenario."""


def normalize_slot(name) -> str:
    """Lower-case and validate a save slot name (None -> the default slot)."""
    slot = (name or DEFAULT_SLOT).strip().lower()
    if not _SLOT_RE.match(slot):
        raise SaveError("Save names can use letters, numbers, '-' and '_' (up to 32 characters).")
    return slot


def content_fingerprint(scenario) -> str:
    """Hash of a scenario's structural ids - what a save's item/room/event
    references depend on. Prose edits don't change it."""
    structure = {
        "rooms": sorted(scenario.rooms),
        "items": sorted(scenario.items),
        "events": sorted(str(e.get("id")) for e in scenario.events),
    }
    return hashlib.sha1(json.dumps(structure, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def snapshot(scenario, rooms: dict, events: list, player, rng) -> dict:
    """Capture the current playthrough as a JSON-safe dict."""
    player_state = {}
    for f in dataclasses.fields(player):
        if f.name in _PLAYER_DERIVED_FIELDS:
            continue
        value = getattr(player, f.name)
        player_state[f.name] = sorted(value) if isinstance(value, set) else value

    room_state = {}
    for room_id, room in rooms.items():
        room_state[room_id] = {
            "description": room["description"],
            "items": list(room["items"]),
            "locked": {d: bool(info["locked"]) for d, info in room["exits"].items() if "locked" in info},
        }

    version, internal, gauss = rng.getstate()
    return {
        "version": SAVE_VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scenario": scenario.name,
        "title": scenario.title,
        "fingerprint": content_fingerprint(scenario),
        "player": player_state,
        "rooms": room_state,
        "events_fired": [e.get("id") for e in events if e.get("fired")],
        "rng": [version, list(internal), gauss],
    }


def apply_snapshot(data: dict, scenario, rooms: dict, events: list, player, rng) -> None:
    """Restore `data` onto a freshly generated world/player, in place.
    Validates everything first so a bad save leaves the game untouched."""
    if not isinstance(data, dict) or data.get("version") != SAVE_VERSION:
        raise SaveError("That save is from an incompatible version of the game.")
    if data.get("scenario") != scenario.name:
        raise SaveError(f"That save belongs to '{data.get('title', data.get('scenario'))}', not this scenario.")
    if data.get("fingerprint") != content_fingerprint(scenario):
        raise SaveError(
            "The scenario's rooms, items or events have changed since this was saved, "
            "so the save can't be loaded safely."
        )

    try:
        saved_rooms = data["rooms"]
        player_state = data["player"]
        fired = set(data["events_fired"])
        version, internal, gauss = data["rng"]
        rng_state = (version, tuple(internal), gauss)
        for room_id, state in saved_rooms.items():
            if room_id not in rooms:
                raise SaveError(f"Save refers to unknown room '{room_id}'.")
            if any(i not in scenario.items for i in state["items"]):
                raise SaveError(f"Save refers to an unknown item in room '{room_id}'.")
        if player_state["location"] not in rooms:
            raise SaveError("Save places you in an unknown room.")
        rng.setstate(rng_state)  # validates shape; nothing else mutated yet
    except SaveError:
        raise
    except (KeyError, TypeError, ValueError) as e:
        raise SaveError(f"That save file is damaged ({type(e).__name__}: {e}).") from e

    for room_id, state in saved_rooms.items():
        room = rooms[room_id]
        room["description"] = state["description"]
        room["items"] = list(state["items"])
        for direction, locked in state.get("locked", {}).items():
            if direction in room["exits"]:
                room["exits"][direction]["locked"] = bool(locked)

    for event in events:
        event["fired"] = event.get("id") in fired

    known = {f.name for f in dataclasses.fields(player)} - _PLAYER_DERIVED_FIELDS
    for name, value in player_state.items():
        if name in known:
            setattr(player, name, set(value) if name == "visited" else value)


def write_save(saves_dir: Path, slot: str, data: dict) -> Path:
    try:
        saves_dir.mkdir(parents=True, exist_ok=True)
        path = saves_dir / f"{slot}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)  # atomic-ish: a crash mid-write can't clobber a good save
        return path
    except OSError as e:
        raise SaveError(f"Couldn't write the save ({e.strerror or e}).") from e


def read_save(saves_dir: Path, slot: str) -> dict:
    path = saves_dir / f"{slot}.json"
    if not path.exists():
        others = list_slots(saves_dir)
        hint = f" Saves you have: {', '.join(others)}." if others else " You have no saves yet."
        raise SaveError(f"No save named '{slot}'.{hint}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SaveError(f"That save file is damaged ({e}).") from e


def list_slots(saves_dir: Path) -> List[str]:
    if not saves_dir.is_dir():
        return []
    return sorted(p.stem for p in saves_dir.glob("*.json"))
