"""
Eldritch - a Lovecraftian terminal adventure.
Entry point / game loop.

The engine itself (this file, plus game/) is generic - all actual story
content (rooms, items, events) lives in data files under data/<scenario>/
and is loaded and validated at startup (see game/content_loader.py).
Pick a scenario with --scenario (defaults to "manor").

Each run generates its own version of the world: room description
variants, item placement, and random events are all resolved from a
seeded RNG at startup (see game/world.py, game/rng.py). Random by
default, so the game plays out differently each time - but a specific
seed can be pinned with --seed for a reproducible run.

A playthrough has real stakes: piece together the scenario's story by
finding all its clues, then reach the exit to win. Sanity bottoming
out, or being caught by the presence that stalks the world, both end
the run.
"""

import argparse
import sys
from pathlib import Path

from game.content_loader import ScenarioError, discover_scenarios, load_scenario
from game.entities import advance_dread, resolve_evasion
from game.parser import parse
from game.player import Player
from game.rng import make_rng
from game.sanity import distort, thresholds_from_dict
from game.world import generate_events, generate_world

PROJECT_ROOT = Path(__file__).resolve().parent


def resolve_data_dir() -> Path:
    """Where scenarios are loaded from. Running from source: data/ beside
    main.py. Packaged .exe: a data/ folder sitting next to the exe wins, so
    scenarios can be added or edited without rebuilding; if there isn't
    one, fall back to the copy bundled inside the exe."""
    if getattr(sys, "frozen", False):
        external = Path(sys.executable).resolve().parent / "data"
        if external.is_dir():
            return external
        return Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) / "data"
    return PROJECT_ROOT / "data"


DATA_DIR = resolve_data_dir()

TURN_CONSUMING_VERBS = {"go", "look", "take", "drop", "use", "rest", "examine"}
DEFAULT_REST_AMOUNT = 15

DEFAULT_PRESENCE_MANIFEST_TEXT = "\nThe air changes. You are no longer alone in this room."

DEFAULT_EVADE_TEXT = "\nYou don't wait to see what it is. You move."

DEFAULT_HIDE_TEXT = (
    "\nYou go still and hold your breath. After a long, silent moment, "
    "whatever it was moves on."
)

DEFAULT_CAUGHT_TEXT = (
    "\nYou hesitate a moment too long. Something closes the distance "
    "between you, and the world is quiet again.\n\n"
    "You are not found. Not by anyone who could still help."
)

DEFAULT_BROKEN_TEXT = (
    "\nSomething in you gives way. The walls are breathing now, or you "
    "are - you can no longer tell which.\n\n"
    "You will still be found here, eventually, sitting very still in a "
    "room that makes sense to no one but you."
)

DEFAULT_WIN_TEXT = (
    "\nIt fits together now - all of it. What this place was for. What "
    "it cost the people who were here. What is, in some sense, still "
    "here.\n\n"
    "The way out opens without resistance this time, as if it were only "
    "ever waiting for you to understand. You do not look back as you "
    "cross the threshold.\n\n"
    "You made it out."
)


def match_item(target, item_ids, scenario, prefer_ids=None):
    """Find an item id in item_ids matching the player's typed target.
    An exact match (full name or item id) always wins outright. A
    looser single-word match (e.g. "key" for "tide-worn key") can be
    ambiguous if several carried items share that word - `prefer_ids`
    (e.g. the unlock_items valid for the current room's locked exits)
    breaks that tie in favor of whichever candidate is actually useful
    here, falling back to the first match otherwise."""
    if not target:
        return None
    word_matches = []
    for item_id in item_ids:
        name = scenario.items[item_id]["name"]
        if target == name or target == item_id:
            return item_id
        if target in name.split():
            word_matches.append(item_id)
    if not word_matches:
        return None
    if prefer_ids:
        for candidate in word_matches:
            if candidate in prefer_ids:
                return candidate
    return word_matches[0]


def clue_progress(player: Player, scenario):
    """Return (clues_found, total_clues, clues_needed_to_win). clues_found
    includes any bonus_clues (e.g. from reading the necronomicon)."""
    total = sum(1 for t in scenario.items.values() if t.get("is_clue"))
    found = sum(1 for i in player.inventory if scenario.items[i].get("is_clue"))
    found += player.bonus_clues
    required = scenario.clues_required if scenario.clues_required is not None else total
    return found, total, required


def has_enough_clues(player: Player, scenario) -> bool:
    found, _total, required = clue_progress(player, scenario)
    return required > 0 and found >= required


def describe_room(player: Player, rooms: dict, scenario, rng) -> None:
    room = rooms[player.location]
    text = distort(room["description"], player.sanity, rng, player.max_sanity, player.tier_thresholds)

    print(f"\n{room['name']}")
    print(text)

    if room.get("safe"):
        print("(This feels like a safe place to rest.)")

    exit_labels = []
    for direction, info in room["exits"].items():
        if info.get("locked"):
            exit_labels.append(f"{direction} (locked)")
        elif "target" not in info:
            exit_labels.append(direction)  # e.g. the win exit - no room to reveal
        elif info["target"] in player.visited:
            exit_labels.append(f"{direction} ({rooms[info['target']]['name']})")
        else:
            exit_labels.append(f"{direction} (Undiscovered)")
    if exit_labels:
        print(f"Exits: {', '.join(exit_labels)}")

    if room["items"]:
        names = [scenario.items[i]["name"] for i in room["items"]]
        print(f"You notice: {', '.join(names)}")


def show_status(player: Player, rooms: dict, scenario) -> None:
    room = rooms[player.location]
    found_clues, total_clues, required_clues = clue_progress(player, scenario)

    print("\n" + "-" * 40)
    print(f"Location: {room['name']}")
    print(f"Sanity: {player.sanity}/{player.max_sanity} ({player.sanity_tier.value})")

    if player.inventory:
        names = [scenario.items[i]["name"] for i in player.inventory]
        print(f"Carrying: {', '.join(names)}")
    else:
        print("Carrying: nothing")

    if required_clues < total_clues:
        print(f"Clues found: {min(found_clues, total_clues)}/{total_clues} ({required_clues} needed to leave)")
    else:
        print(f"Clues found: {min(found_clues, total_clues)}/{total_clues}")
    print(f"Rooms explored: {len(player.visited)}/{len(rooms)}")
    print("-" * 40)


def check_events(player: Player, rooms: dict, events: list, rng) -> None:
    """Roll for any event tied to the player's current room. One-shot
    events (the default) never fire again once used; events marked
    repeat: true can fire again on future visits."""
    room_id = player.location
    for event in events:
        if event.get("fired") and not event.get("repeat"):
            continue
        if room_id not in event["rooms"]:
            continue
        if rng.random() < event["chance"]:
            if not event.get("repeat"):
                event["fired"] = True
            print(f"\n{event['text']}")
            effect = event.get("sanity_effect")
            if effect:
                player.adjust_sanity(effect)


def handle_command(cmd, player: Player, rooms: dict, events: list, rng, scenario) -> str:
    """Execute a parsed command. Returns one of:
    'continue', 'quit', 'win', 'caught', 'broken'."""
    room = rooms[player.location]
    just_evaded = False

    # If the presence is active, the only valid responses are to flee to
    # another room or hide - anything else, including looking around or
    # checking your inventory, means you're caught.
    if player.presence_active:
        if cmd.verb == "quit":
            print("\nYou step back from the threshold. Some things are better left unseen.")
            return "quit"

        if cmd.verb == "hide":
            resolve_evasion(player)
            just_evaded = True
            print(scenario.threat.get("hide_text") or DEFAULT_HIDE_TEXT)
            return "continue"

        can_flee = (
            cmd.verb == "go"
            and cmd.direction
            and cmd.direction in room["exits"]
            and not room["exits"][cmd.direction].get("locked")
            and not room["exits"][cmd.direction].get("requires_all_clues")
        )
        if can_flee:
            resolve_evasion(player)
            just_evaded = True
            print(scenario.threat.get("evade_text") or DEFAULT_EVADE_TEXT)
            # Fall through to the normal 'go' handling below.
        else:
            print(scenario.threat.get("caught_text") or DEFAULT_CAUGHT_TEXT)
            return "caught"

    if cmd.verb == "quit":
        print("\nYou step back from the threshold. Some things are better left unseen.")
        return "quit"

    elif cmd.verb == "look":
        describe_room(player, rooms, scenario, rng)

    elif cmd.verb == "examine":
        if not cmd.target:
            describe_room(player, rooms, scenario, rng)
        else:
            scenery = room.get("scenery", {})
            scenery_text = None
            for noun, text in scenery.items():
                if cmd.target == noun or cmd.target in noun.split():
                    scenery_text = text
                    break
            if scenery_text:
                print(f"\n{scenery_text}")
            else:
                matched = match_item(cmd.target, room["items"] + player.inventory, scenario)
                if matched:
                    print(f"\n{scenario.items[matched].get('description', 'Nothing special about it.')}")
                else:
                    print("You see nothing special about that.")

    elif cmd.verb == "go":
        direction = cmd.direction
        if not direction:
            print("Go where?")
        elif direction not in room["exits"]:
            print("You can't go that way.")
        else:
            exit_info = room["exits"][direction]
            if exit_info.get("requires_all_clues"):
                if has_enough_clues(player, scenario):
                    print(scenario.win_text or DEFAULT_WIN_TEXT)
                    return "win"
                print(exit_info.get("locked_text", "That way is blocked."))
            elif exit_info.get("locked"):
                print(exit_info.get("locked_text", "That way is locked."))
            else:
                player.location = exit_info["target"]
                player.visited.add(player.location)
                describe_room(player, rooms, scenario, rng)
                check_events(player, rooms, events, rng)

    elif cmd.verb == "inventory":
        if player.inventory:
            names = [scenario.items[i]["name"] for i in player.inventory]
            print("You are carrying: " + ", ".join(names))
        else:
            print("You are carrying nothing.")

    elif cmd.verb == "take":
        if not cmd.target:
            print("Take what?")
        else:
            matched = match_item(cmd.target, room["items"], scenario)
            if not matched:
                print("You don't see that here.")
            else:
                room["items"].remove(matched)
                player.add_item(matched)
                template = scenario.items[matched]
                print(f"You take the {template['name']}.")
                sanity_effect = template.get("on_take_sanity")
                if sanity_effect:
                    player.adjust_sanity(sanity_effect)
                    flavor = template.get("on_take_text")
                    if flavor:
                        print(flavor)

    elif cmd.verb == "drop":
        if not cmd.target:
            print("Drop what?")
        else:
            matched = match_item(cmd.target, player.inventory, scenario)
            if not matched:
                print("You aren't carrying that.")
            else:
                player.remove_item(matched)
                room["items"].append(matched)
                print(f"You set down the {scenario.items[matched]['name']}.")

    elif cmd.verb == "use":
        if not cmd.target:
            print("Use what?")
        else:
            unlock_candidates = {
                info.get("unlock_item")
                for info in room["exits"].values()
                if info.get("locked") and info.get("unlock_item")
            }
            matched = match_item(cmd.target, player.inventory, scenario, prefer_ids=unlock_candidates)
            if not matched:
                print("You aren't carrying that.")
            elif matched == "necronomicon":
                if player.necronomicon_read:
                    print("You've already read as much of it as you're willing to. The rest can stay unread.")
                else:
                    cost = player.sanity // 2
                    player.adjust_sanity(-cost)
                    player.bonus_clues += 2
                    player.necronomicon_read = True
                    player.regeneration_disabled = True
                    print(
                        "\nYou read further this time, and further than that.\n\n"
                        "What you understand afterward isn't comfortable, but it's "
                        "useful - the shape of two things you needed to know clicks "
                        "into place. The cost is immediate: something in you that "
                        "was holding steady simply stops. You don't think it's "
                        "coming back, not on this trip."
                    )
            else:
                template = scenario.items[matched]
                restore_amount = template.get("on_use_sanity")
                if restore_amount:
                    if player.regeneration_disabled:
                        print("It should help. It doesn't, not anymore.")
                    else:
                        player.remove_item(matched)
                        player.adjust_sanity(restore_amount)
                        print(template.get("on_use_text", "That helped, a little."))
                else:
                    unlocked_anything = False
                    for info in room["exits"].values():
                        if info.get("locked") and info.get("unlock_item") == matched:
                            info["locked"] = False
                            print(info.get("unlock_text", "Something unlocks."))
                            unlocked_anything = True
                    if not unlocked_anything:
                        print("Nothing happens.")

    elif cmd.verb in ("save", "load"):
        print("Saving isn't wired up yet - that's coming in a later step.")

    elif cmd.verb == "status":
        show_status(player, rooms, scenario)

    elif cmd.verb == "hide":
        print("There's nothing to hide from right now.")

    elif cmd.verb == "rest":
        if player.regeneration_disabled:
            print("Whatever peace this place once offered, you burned through when you read too far. It does nothing for you now.")
        elif room.get("safe"):
            amount = room.get("rest_amount", DEFAULT_REST_AMOUNT)
            player.adjust_sanity(amount)
            print(f"\n{room.get('rest_text', 'You allow yourself a moment of stillness. It helps, if only a little.')}")
        else:
            print("There's nothing here that makes it feel safe to stop.")

    elif cmd.verb == "help":
        print(
            "Commands: look, examine <thing>, go <direction>, take <item>, "
            "drop <item>, use <item>, inventory, status, hide, rest, quit"
        )

    elif cmd.verb == "unknown":
        print("You're not sure how to do that.")

    elif cmd.verb == "empty":
        pass

    if cmd.verb in TURN_CONSUMING_VERBS and not player.presence_active and not just_evaded:
        current_room = rooms[player.location]  # re-fetch: 'go' may have just moved the player
        if not current_room.get("safe"):
            risk_multiplier = current_room.get("risk_multiplier", 1.0) * scenario.dread_scale
            if advance_dread(player, rng, scenario.threat, risk_multiplier):
                print(scenario.threat.get("manifest_text") or DEFAULT_PRESENCE_MANIFEST_TEXT)

    if player.sanity <= 0:
        print(scenario.broken_text or DEFAULT_BROKEN_TEXT)
        return "broken"

    return "continue"


def resolve_scenario_choice(raw: str, scenario_ids: list):
    """Parse one line of menu input against the numbered scenario list.
    Returns a scenario id, the string 'random' (for the trailing Random
    option), or None if the input doesn't resolve to a valid choice."""
    raw = raw.strip()
    if not raw.isdigit():
        return None
    idx = int(raw)
    if 1 <= idx <= len(scenario_ids):
        return scenario_ids[idx - 1]
    if idx == len(scenario_ids) + 1:
        return "random"
    return None


def choose_scenario_interactively(scenarios: list, rng) -> str:
    """Print a numbered menu of available scenarios plus a Random
    option, and loop until the player picks a valid one. Returns the
    chosen scenario's folder id (resolving Random via `rng`, so it's
    reproducible under --seed like everything else)."""
    ids = [s["id"] for s in scenarios]

    print("\nAvailable scenarios:")
    for i, s in enumerate(scenarios, start=1):
        print(f"  {i}. {s['title']}")
    print(f"  {len(scenarios) + 1}. Random")

    while True:
        try:
            raw = input("\nChoose a scenario (number): ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            sys.exit(0)

        choice = resolve_scenario_choice(raw, ids)
        if choice == "random":
            return rng.choice(ids)
        if choice is not None:
            return choice
        print("Please enter a valid number from the list.")


def main() -> None:
    arg_parser = argparse.ArgumentParser(description="Eldritch - a terminal adventure")
    arg_parser.add_argument(
        "--scenario", default=None,
        help="Which adventure to load from data/ (skips the selection menu if given)",
    )
    arg_parser.add_argument(
        "--seed", type=int, default=None,
        help="Pin a specific world seed for a reproducible run",
    )
    arg_parser.add_argument(
        "--show-seed", action="store_true",
        help="Print the seed used this run, for debugging",
    )
    args = arg_parser.parse_args()

    rng, seed = make_rng(args.seed)

    if args.scenario:
        scenario_id = args.scenario
    else:
        print("=" * 60)
        print("ELDRITCH")
        print("=" * 60)
        scenarios = discover_scenarios(DATA_DIR)
        if not scenarios:
            print(f"No scenarios found under {DATA_DIR}.", file=sys.stderr)
            sys.exit(1)
        scenario_id = choose_scenario_interactively(scenarios, rng)

    try:
        scenario = load_scenario(DATA_DIR / scenario_id)
    except ScenarioError as e:
        print(f"Could not load scenario '{scenario_id}':\n{e}", file=sys.stderr)
        sys.exit(1)

    rooms = generate_world(scenario, rng)
    events = generate_events(scenario, rng)
    player = Player(
        location=scenario.start_room,
        sanity=scenario.max_sanity,
        max_sanity=scenario.max_sanity,
        tier_thresholds=thresholds_from_dict(scenario.sanity_tier_thresholds),
    )
    player.visited.add(player.location)

    print("=" * 60)
    print("ELDRITCH")
    print(scenario.title)
    print("=" * 60)
    if args.show_seed:
        print(f"[seed: {seed}]")
    if scenario.intro:
        print(f"\n{scenario.intro}")

    describe_room(player, rooms, scenario, rng)

    running = True
    while running:
        try:
            raw = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        cmd = parse(raw)
        outcome = handle_command(cmd, player, rooms, events, rng, scenario)
        running = outcome == "continue"


def pause_if_packaged() -> None:
    """In the packaged .exe, a double-click opens a console that closes the
    instant the game ends - hiding the ending (or any startup error).
    Hold it open until Enter. No-op when run normally via `python main.py`."""
    if not getattr(sys, "frozen", False):
        return
    try:
        input("\nPress Enter to exit...")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    try:
        main()
    finally:
        pause_if_packaged()
