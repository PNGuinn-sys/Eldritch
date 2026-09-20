"""
Smoke tests for the parser, sanity system, world generation, and the
scenario loader/validator.

Run directly with: python tests/test_engine.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game.content_loader import Scenario, discover_scenarios, load_scenario, validate_scenario
from game.parser import parse
from game.rng import make_rng
from game.sanity import SanityTier, distort, tier_for
from game.world import generate_events, generate_world

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANOR_SCENARIO = load_scenario(PROJECT_ROOT / "data" / "manor")


# --- Parser ----------------------------------------------------------------

def test_parser_basic_verbs():
    assert parse("look").verb == "look"
    assert parse("l").verb == "look"
    assert parse("").verb == "empty"
    assert parse("asdkjhaskjd").verb == "unknown"


def test_parser_movement():
    cmd = parse("go north")
    assert cmd.verb == "go" and cmd.direction == "north"

    cmd = parse("n")
    assert cmd.verb == "go" and cmd.direction == "north"


def test_parser_target():
    cmd = parse("take brass key")
    assert cmd.verb == "take"
    assert cmd.target == "brass key"


# --- Sanity ------------------------------------------------------------------

def test_sanity_tiers():
    assert tier_for(100) == SanityTier.LUCID
    assert tier_for(80) == SanityTier.LUCID
    assert tier_for(79) == SanityTier.UNEASY
    assert tier_for(50) == SanityTier.UNEASY
    assert tier_for(49) == SanityTier.FRAYING
    assert tier_for(25) == SanityTier.FRAYING
    assert tier_for(24) == SanityTier.BROKEN
    assert tier_for(0) == SanityTier.BROKEN


def test_distort_lucid_unchanged():
    text = "The room is quiet."
    assert distort(text, 100) == text


def test_sanity_tiers_scale_with_custom_max_sanity():
    # Same percentage breakpoints (80/50/25%), applied against a
    # scenario-specific pool instead of assuming it's always /100.
    assert tier_for(120, max_sanity=150) == SanityTier.LUCID    # exactly 80%
    assert tier_for(119, max_sanity=150) == SanityTier.UNEASY   # just under 80%
    assert tier_for(75, max_sanity=150) == SanityTier.UNEASY    # exactly 50%
    assert tier_for(74, max_sanity=150) == SanityTier.FRAYING   # just under 50%
    assert tier_for(38, max_sanity=150) == SanityTier.FRAYING   # just over 25%
    assert tier_for(37, max_sanity=150) == SanityTier.BROKEN    # just under 25%


# --- Scenario loading & validation --------------------------------------------

def test_manor_scenario_loads_and_validates():
    assert MANOR_SCENARIO.start_room in MANOR_SCENARIO.rooms
    assert len(MANOR_SCENARIO.rooms) == 13
    assert validate_scenario(MANOR_SCENARIO) == []


def test_second_scenario_loads_and_validates():
    """Proves the engine is genuinely adventure-agnostic, not just
    tuned to the manor's specific content."""
    hollow_tide = load_scenario(PROJECT_ROOT / "data" / "hollow_tide")
    assert hollow_tide.start_room in hollow_tide.rooms
    assert validate_scenario(hollow_tide) == []
    assert sum(1 for i in hollow_tide.items.values() if i.get("is_clue")) > 0


def test_validator_catches_bad_exit_target():
    scenario = Scenario(
        name="broken", title="Broken", description="", start_room="a",
        rooms={"a": {
            "name": "Room A",
            "description_variants": ["A room."],
            "exits": {"north": {"target": "nowhere"}},
        }},
        items={}, events=[],
    )
    errors = validate_scenario(scenario)
    assert any("unknown room 'nowhere'" in e for e in errors)


def test_validator_catches_locked_exit_without_unlock_item():
    scenario = Scenario(
        name="broken", title="Broken", description="", start_room="a",
        rooms={
            "a": {
                "name": "Room A",
                "description_variants": ["A room."],
                "exits": {"north": {"target": "b", "locked": True}},
            },
            "b": {
                "name": "Room B",
                "description_variants": ["Another room."],
                "exits": {},
            },
        },
        items={}, events=[],
    )
    errors = validate_scenario(scenario)
    assert any("no unlock_item" in e for e in errors)


def test_validator_catches_clue_without_win_exit():
    scenario = Scenario(
        name="broken", title="Broken", description="", start_room="a",
        rooms={"a": {
            "name": "Room A",
            "description_variants": ["A room."],
            "exits": {},
        }},
        items={"clue_1": {"name": "a clue", "valid_rooms": ["a"], "is_clue": True}},
        events=[],
    )
    errors = validate_scenario(scenario)
    assert any("requires_all_clues" in e for e in errors)


def test_validator_catches_item_in_unknown_room():
    scenario = Scenario(
        name="broken", title="Broken", description="", start_room="a",
        rooms={"a": {
            "name": "Room A",
            "description_variants": ["A room."],
            "exits": {},
        }},
        items={"thing": {"name": "a thing", "valid_rooms": ["nowhere"]}},
        events=[],
    )
    errors = validate_scenario(scenario)
    assert any("unknown room 'nowhere'" in e for e in errors)


def test_validator_catches_clues_required_exceeding_total():
    scenario = Scenario(
        name="broken", title="Broken", description="", start_room="a",
        rooms={"a": {
            "name": "Room A",
            "description_variants": ["A room."],
            "exits": {"out": {"requires_all_clues": True, "locked_text": "no"}},
        }},
        items={"clue_1": {"name": "a clue", "valid_rooms": ["a"], "is_clue": True}},
        events=[],
        clues_required=5,
    )
    errors = validate_scenario(scenario)
    assert any("clues_required" in e for e in errors)


# --- World generation ------------------------------------------------------------

def test_world_generation_is_deterministic_for_a_seed():
    rng1, _ = make_rng(12345)
    world1 = generate_world(MANOR_SCENARIO, rng1)

    rng2, _ = make_rng(12345)
    world2 = generate_world(MANOR_SCENARIO, rng2)

    assert world1 == world2


def test_items_are_placed_in_a_valid_room():
    rng, _ = make_rng(42)
    world = generate_world(MANOR_SCENARIO, rng)

    for item_id, template in MANOR_SCENARIO.items.items():
        rooms_containing_item = [
            room_id for room_id, room in world.items() if item_id in room["items"]
        ]
        assert len(rooms_containing_item) == 1
        assert rooms_containing_item[0] in template["valid_rooms"]


def test_cellar_starts_locked():
    rng, _ = make_rng(7)
    world = generate_world(MANOR_SCENARIO, rng)
    assert world["corridor"]["exits"]["down"]["locked"] is True


# --- Engine integration (via main.handle_command) -------------------------------

def test_visited_rooms_tracked_on_movement():
    import io
    from contextlib import redirect_stdout

    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)
    player = Player(location=MANOR_SCENARIO.start_room)
    player.visited.add(player.location)

    with redirect_stdout(io.StringIO()):
        game_main.handle_command(parse("go north"), player, rooms, events, rng, MANOR_SCENARIO)

    assert player.location == "corridor"
    assert player.visited == {"foyer", "corridor"}


def test_status_output_includes_key_fields():
    import io
    from contextlib import redirect_stdout

    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    player = Player(
        location=MANOR_SCENARIO.start_room,
        sanity=MANOR_SCENARIO.max_sanity,
        max_sanity=MANOR_SCENARIO.max_sanity,
    )
    player.visited.add(player.location)
    player.add_item("brass_key")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        game_main.show_status(player, rooms, MANOR_SCENARIO)
    output = buffer.getvalue()

    assert rooms[MANOR_SCENARIO.start_room]["name"] in output
    assert f"Sanity: {MANOR_SCENARIO.max_sanity}/{MANOR_SCENARIO.max_sanity}" in output
    assert "brass key" in output
    assert "Rooms explored: 1/" in output
    assert "needed to leave" in output  # manor uses a partial clue threshold


def test_advance_dread_manifests_at_threshold():
    from game.entities import DREAD_THRESHOLD, advance_dread
    from game.player import Player

    class AlwaysHitsRandom:
        def random(self):
            return 0.0  # always below any chance threshold

    player = Player(location="foyer")
    rng_stub = AlwaysHitsRandom()

    manifested = False
    for _ in range(DREAD_THRESHOLD):
        manifested = advance_dread(player, rng_stub)

    assert manifested is True
    assert player.presence_active is True
    assert player.dread == DREAD_THRESHOLD


def test_reaching_out_with_all_clues_wins():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(5)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)

    player = Player(location="foyer")
    player.visited.add(player.location)
    for item_id, template in MANOR_SCENARIO.items.items():
        if template.get("is_clue"):
            player.add_item(item_id)

    outcome = game_main.handle_command(parse("go out"), player, rooms, events, rng, MANOR_SCENARIO)
    assert outcome == "win"


def test_reaching_out_without_all_clues_is_blocked():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(5)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)

    player = Player(location="foyer")
    player.visited.add(player.location)

    outcome = game_main.handle_command(parse("go out"), player, rooms, events, rng, MANOR_SCENARIO)
    assert outcome == "continue"
    assert player.location == "foyer"


def test_caught_if_not_evading_when_presence_active():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(9)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)

    player = Player(location="foyer")
    player.presence_active = True

    outcome = game_main.handle_command(parse("look"), player, rooms, events, rng, MANOR_SCENARIO)
    assert outcome == "caught"


def test_fleeing_resolves_presence():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(11)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)

    player = Player(location="foyer")
    player.visited.add(player.location)
    player.presence_active = True
    player.dread = 3

    outcome = game_main.handle_command(parse("go north"), player, rooms, events, rng, MANOR_SCENARIO)
    assert outcome == "continue"
    assert player.presence_active is False
    assert player.dread == 0
    assert player.location == "corridor"


def test_hiding_resolves_presence():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(13)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)

    player = Player(location="foyer")
    player.presence_active = True
    player.dread = 3

    outcome = game_main.handle_command(parse("hide"), player, rooms, events, rng, MANOR_SCENARIO)
    assert outcome == "continue"
    assert player.presence_active is False
    assert player.dread == 0


def test_rest_recovers_sanity_in_safe_room():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)
    safe_room_id = next(r for r, room in rooms.items() if room.get("safe"))

    player = Player(location=safe_room_id, sanity=50, max_sanity=MANOR_SCENARIO.max_sanity)
    player.visited.add(player.location)

    game_main.handle_command(parse("rest"), player, rooms, events, rng, MANOR_SCENARIO)
    assert player.sanity > 50


def test_rest_does_nothing_in_unsafe_room():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)
    unsafe_room_id = next(r for r, room in rooms.items() if not room.get("safe"))

    player = Player(location=unsafe_room_id, sanity=50, max_sanity=MANOR_SCENARIO.max_sanity)
    player.visited.add(player.location)

    game_main.handle_command(parse("rest"), player, rooms, events, rng, MANOR_SCENARIO)
    assert player.sanity == 50


def test_safe_room_pauses_dread_accumulation():
    import main as game_main
    from game.player import Player

    class AlwaysHitsRandom:
        def random(self):
            return 0.0  # would always build dread, if it were rolled at all

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)
    safe_room_id = next(r for r, room in rooms.items() if room.get("safe"))

    player = Player(location=safe_room_id, max_sanity=MANOR_SCENARIO.max_sanity,
                     sanity=MANOR_SCENARIO.max_sanity)
    player.visited.add(player.location)

    stub_rng = AlwaysHitsRandom()
    for _ in range(5):
        game_main.handle_command(parse("look"), player, rooms, events, stub_rng, MANOR_SCENARIO)

    assert player.dread == 0
    assert player.presence_active is False


def test_curative_item_restores_sanity_and_is_consumed():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)

    player = Player(location="foyer", sanity=50, max_sanity=MANOR_SCENARIO.max_sanity)
    player.visited.add(player.location)
    player.add_item("silver_locket")

    game_main.handle_command(parse("use silver locket"), player, rooms, events, rng, MANOR_SCENARIO)

    assert player.sanity > 50
    assert not player.has_item("silver_locket")


def test_validator_catches_clue_that_is_also_consumable():
    scenario = Scenario(
        name="broken", title="Broken", description="", start_room="a",
        rooms={"a": {
            "name": "Room A",
            "description_variants": ["A room."],
            "exits": {"out": {"requires_all_clues": True, "locked_text": "no"}},
        }},
        items={"oops": {
            "name": "a confused item", "valid_rooms": ["a"],
            "is_clue": True, "on_use_sanity": 10,
        }},
        events=[],
    )
    errors = validate_scenario(scenario)
    assert any("is both is_clue and on_use_sanity" in e for e in errors)


def test_use_disambiguates_ambiguous_key_word_toward_the_one_that_unlocks():
    import main as game_main
    from game.player import Player

    hollow_tide = load_scenario(PROJECT_ROOT / "data" / "hollow_tide")
    rng, _ = make_rng(1)
    rooms = generate_world(hollow_tide, rng)
    events = generate_events(hollow_tide, rng)

    player = Player(location="cannery", max_sanity=hollow_tide.max_sanity, sanity=hollow_tide.max_sanity)
    player.visited.add(player.location)
    # Carry an unrelated key first, then the one that actually unlocks
    # the cannery's tunnels exit - a bare "use key" should still find
    # tide_worn_key, not whichever key happens to be first in inventory.
    player.add_item("estate_key")
    player.add_item("tide_worn_key")

    game_main.handle_command(parse("use key"), player, rooms, events, rng, hollow_tide)
    assert rooms["cannery"]["exits"]["down"]["locked"] is False


def test_reanimator_scenario_loads_and_validates():
    reanimator = load_scenario(PROJECT_ROOT / "data" / "reanimator")
    assert reanimator.start_room in reanimator.rooms
    assert validate_scenario(reanimator) == []


def test_discover_scenarios_finds_manor_and_hollow_tide_but_not_template():
    scenarios = discover_scenarios(PROJECT_ROOT / "data")
    ids = {s["id"] for s in scenarios}
    assert "manor" in ids
    assert "hollow_tide" in ids
    assert "reanimator" in ids
    assert "_template" not in ids


def test_discover_scenarios_reads_titles_from_manifest():
    scenarios = discover_scenarios(PROJECT_ROOT / "data")
    titles = {s["id"]: s["title"] for s in scenarios}
    assert titles["manor"] == "The Manor"
    assert titles["hollow_tide"] == "Hollow Tide"


def test_resolve_scenario_choice_valid_number():
    from main import resolve_scenario_choice
    assert resolve_scenario_choice("2", ["manor", "hollow_tide"]) == "hollow_tide"


def test_resolve_scenario_choice_random_option():
    from main import resolve_scenario_choice
    # With 2 scenarios, option 3 is the trailing "Random" entry.
    assert resolve_scenario_choice("3", ["manor", "hollow_tide"]) == "random"


def test_resolve_scenario_choice_rejects_invalid_input():
    from main import resolve_scenario_choice
    assert resolve_scenario_choice("0", ["manor", "hollow_tide"]) is None
    assert resolve_scenario_choice("4", ["manor", "hollow_tide"]) is None
    assert resolve_scenario_choice("abc", ["manor", "hollow_tide"]) is None
    assert resolve_scenario_choice("", ["manor", "hollow_tide"]) is None


def test_choose_scenario_interactively_resolves_random_via_rng():
    from main import choose_scenario_interactively
    from unittest.mock import patch

    scenarios = [{"id": "manor", "title": "The Manor"}, {"id": "hollow_tide", "title": "Hollow Tide"}]
    rng, _ = make_rng(1)

    with patch("builtins.input", return_value="3"):
        choice = choose_scenario_interactively(scenarios, rng)
    assert choice in ("manor", "hollow_tide")


def test_necronomicon_auto_injected_when_scenario_has_none():
    assert "necronomicon" in MANOR_SCENARIO.items
    assert set(MANOR_SCENARIO.items["necronomicon"]["valid_rooms"]) == set(MANOR_SCENARIO.rooms.keys())


def test_necronomicon_scenario_override_is_kept():
    hollow_tide = load_scenario(PROJECT_ROOT / "data" / "hollow_tide")
    assert hollow_tide.items["necronomicon"]["valid_rooms"] == ["lodge"]


def test_examine_necronomicon_has_no_side_effects():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    player = Player(location="foyer", max_sanity=100, sanity=100)
    player.add_item("necronomicon")

    game_main.handle_command(parse("examine necronomicon"), player, rooms, [], rng, MANOR_SCENARIO)

    assert player.sanity == 100
    assert player.bonus_clues == 0
    assert player.necronomicon_read is False
    assert player.has_item("necronomicon")


def test_reading_necronomicon_costs_half_current_sanity_and_grants_two_clues():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    player = Player(location="foyer", max_sanity=100, sanity=100)
    player.add_item("necronomicon")

    game_main.handle_command(parse("use necronomicon"), player, rooms, [], rng, MANOR_SCENARIO)

    assert player.sanity == 50  # half of the CURRENT 100, not max_sanity
    assert player.bonus_clues == 2
    assert player.necronomicon_read is True
    assert player.regeneration_disabled is True


def test_reading_necronomicon_twice_only_applies_once():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    player = Player(location="foyer", max_sanity=100, sanity=100)
    player.add_item("necronomicon")

    game_main.handle_command(parse("use necronomicon"), player, rooms, [], rng, MANOR_SCENARIO)
    game_main.handle_command(parse("use necronomicon"), player, rooms, [], rng, MANOR_SCENARIO)

    assert player.sanity == 50  # unchanged by the second attempt
    assert player.bonus_clues == 2  # not 4


def test_regeneration_disabled_blocks_rest_and_curatives():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    safe_room_id = next(r for r, room in rooms.items() if room.get("safe"))

    player = Player(location=safe_room_id, max_sanity=100, sanity=50, regeneration_disabled=True)
    player.visited.add(player.location)
    player.add_item("silver_locket")  # a curative in the manor

    game_main.handle_command(parse("rest"), player, rooms, [], rng, MANOR_SCENARIO)
    assert player.sanity == 50

    game_main.handle_command(parse("use silver locket"), player, rooms, [], rng, MANOR_SCENARIO)
    assert player.sanity == 50
    assert player.has_item("silver_locket")  # not consumed, since it didn't work


def test_bonus_clues_count_toward_the_win_threshold():
    from main import clue_progress
    from game.player import Player

    player = Player(location="foyer", bonus_clues=2)
    found, total, required = clue_progress(player, MANOR_SCENARIO)
    assert found == 2


def test_scenario_can_override_threat_flavor_text():
    import main as game_main
    from game.player import Player

    hollow_tide = load_scenario(PROJECT_ROOT / "data" / "hollow_tide")
    rng, _ = make_rng(1)
    rooms = generate_world(hollow_tide, rng)
    events = generate_events(hollow_tide, rng)

    player = Player(location=hollow_tide.start_room, max_sanity=hollow_tide.max_sanity,
                     sanity=hollow_tide.max_sanity)
    player.presence_active = True

    import io
    from contextlib import redirect_stdout
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        outcome = game_main.handle_command(parse("look"), player, rooms, events, rng, hollow_tide)
    assert outcome == "caught"
    assert "shambling" not in buffer.getvalue()  # sanity check on the assertion itself
    assert "running has stopped being the point" in buffer.getvalue()


def test_risk_multiplier_increases_dread_chance():
    from game.entities import advance_dread
    from game.player import Player

    class FixedRandom:
        def __init__(self, value):
            self.value = value

        def random(self):
            return self.value

    threat_config = {"threshold": 5, "chance_by_tier": {"lucid": 0.10, "uneasy": 0.2, "fraying": 0.3, "broken": 0.5}}

    # A roll of 0.15 misses the base lucid chance (0.10) but hits once
    # a risk_multiplier of 2.0 doubles it to 0.20.
    player_a = Player(location="x", max_sanity=100, sanity=100)
    advance_dread(player_a, FixedRandom(0.15), threat_config, risk_multiplier=1.0)
    assert player_a.dread == 0

    player_b = Player(location="x", max_sanity=100, sanity=100)
    advance_dread(player_b, FixedRandom(0.15), threat_config, risk_multiplier=2.0)
    assert player_b.dread == 1


def test_sanity_tier_thresholds_can_be_overridden():
    from game.sanity import thresholds_from_dict, tier_for

    custom = thresholds_from_dict({"lucid": 0.9, "uneasy": 0.6, "fraying": 0.3})
    assert tier_for(95, 100, custom) == SanityTier.LUCID
    assert tier_for(85, 100, custom) == SanityTier.UNEASY
    assert tier_for(50, 100, custom) == SanityTier.FRAYING
    assert tier_for(20, 100, custom) == SanityTier.BROKEN


def test_validator_catches_invalid_tier_threshold_ordering():
    scenario = Scenario(
        name="broken", title="Broken", description="", start_room="a",
        rooms={"a": {"name": "Room A", "description_variants": ["A room."], "exits": {}}},
        items={}, events=[],
        sanity_tier_thresholds={"lucid": 0.5, "uneasy": 0.6, "fraying": 0.25},
    )
    errors = validate_scenario(scenario)
    assert any("sanity_tier_thresholds must satisfy" in e for e in errors)


def test_unvisited_exit_shows_undiscovered():
    import io
    from contextlib import redirect_stdout

    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    player = Player(location="foyer")
    player.visited.add(player.location)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        game_main.describe_room(player, rooms, MANOR_SCENARIO, rng)
    output = buffer.getvalue()

    assert "Undiscovered" in output
    assert rooms["corridor"]["name"] not in output  # not visited yet, name shouldn't leak


def test_visited_exit_shows_room_name():
    import io
    from contextlib import redirect_stdout

    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    player = Player(location="foyer")
    player.visited.add(player.location)
    player.visited.add("corridor")  # as if the player has already been there

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        game_main.describe_room(player, rooms, MANOR_SCENARIO, rng)
    output = buffer.getvalue()

    assert rooms["corridor"]["name"] in output


def test_locked_exit_shows_locked_regardless_of_visited():
    import io
    from contextlib import redirect_stdout

    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    player = Player(location="corridor")
    player.visited.add(player.location)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        game_main.describe_room(player, rooms, MANOR_SCENARIO, rng)
    output = buffer.getvalue()

    assert "down (locked)" in output


def test_win_exit_shows_bare_direction_no_room_name():
    import io
    from contextlib import redirect_stdout

    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    player = Player(location="foyer")
    player.visited.add(player.location)

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        game_main.describe_room(player, rooms, MANOR_SCENARIO, rng)
    output = buffer.getvalue()

    assert "out" in output
    assert "out (" not in output


def test_repeatable_event_can_fire_more_than_once():
    import main as game_main
    from game.player import Player

    class AlwaysHitsRandom:
        def random(self):
            return 0.0

    events = [{"id": "ambient", "rooms": ["a"], "chance": 0.5, "text": "...", "fired": False, "repeat": True}]
    rooms = {"a": {"name": "Room A", "description": "d", "exits": {}, "items": []}}
    player = Player(location="a")

    stub = AlwaysHitsRandom()
    game_main.check_events(player, rooms, events, stub)
    game_main.check_events(player, rooms, events, stub)
    game_main.check_events(player, rooms, events, stub)

    assert player.sanity == 100  # no sanity_effect on this test event, just confirming no crash
    assert events[0]["fired"] is False  # repeat events never get marked as permanently fired


def test_one_shot_event_only_fires_once():
    import main as game_main
    from game.player import Player

    class AlwaysHitsRandom:
        def random(self):
            return 0.0

    calls = []
    events = [{"id": "story_beat", "rooms": ["a"], "chance": 0.5, "text": "!!!", "fired": False}]
    rooms = {"a": {"name": "Room A", "description": "d", "exits": {}, "items": []}}
    player = Player(location="a")

    import io
    from contextlib import redirect_stdout
    stub = AlwaysHitsRandom()
    for _ in range(3):
        buf = io.StringIO()
        with redirect_stdout(buf):
            game_main.check_events(player, rooms, events, stub)
        calls.append("!!!" in buf.getvalue())

    assert calls == [True, False, False]


def test_examine_shows_item_description():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(1)
    rooms = generate_world(MANOR_SCENARIO, rng)
    player = Player(location="foyer")
    player.add_item("brass_key")

    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        game_main.handle_command(parse("examine brass key"), player, rooms, [], rng, MANOR_SCENARIO)
    assert MANOR_SCENARIO.items["brass_key"]["description"] in buf.getvalue()


def test_examine_shows_room_scenery():
    import main as game_main
    from game.player import Player

    rooms = {"a": {
        "name": "Room A", "description": "d", "exits": {}, "items": [],
        "scenery": {"mural": "A strange mural of spirals."},
    }}
    player = Player(location="a")
    rng, _ = make_rng(1)

    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        game_main.handle_command(parse("examine mural"), player, rooms, [], rng, MANOR_SCENARIO)
    assert "strange mural of spirals" in buf.getvalue()


def test_partial_clue_threshold_allows_win_without_all_clues():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(5)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)

    clue_ids = [i for i, t in MANOR_SCENARIO.items.items() if t.get("is_clue")]
    assert MANOR_SCENARIO.clues_required is not None
    assert MANOR_SCENARIO.clues_required < len(clue_ids)

    player = Player(location="foyer")
    player.visited.add(player.location)
    for item_id in clue_ids[:MANOR_SCENARIO.clues_required]:
        player.add_item(item_id)

    outcome = game_main.handle_command(parse("go out"), player, rooms, events, rng, MANOR_SCENARIO)
    assert outcome == "win"


def test_sanity_reaching_zero_ends_game():
    import main as game_main
    from game.player import Player

    rng, _ = make_rng(21)
    rooms = generate_world(MANOR_SCENARIO, rng)
    events = generate_events(MANOR_SCENARIO, rng)

    player = Player(location="foyer")
    player.visited.add(player.location)
    player.adjust_sanity(-97)  # sanity now 3
    player.adjust_sanity(-10)  # clamped to 0

    outcome = game_main.handle_command(parse("status"), player, rooms, events, rng, MANOR_SCENARIO)
    assert outcome == "broken"
    assert player.sanity == 0


def run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
