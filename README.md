# ELDRITCH
### A Lovecraftian Terminal Adventure

> *"The most merciful thing in the world, I think, is the inability of the human mind to correlate all its contents."*

**Status:** 🏚️🌊🔪 Three distinct, fully data-driven scenarios — "The Manor,"
"Hollow Tide," and "The Reagent" — plus a scenario-selection menu, proving
the engine scales in size, personality, and content across adventures
**Working title** — open to renaming once the story takes shape.

---

## About

A text-based, terminal-only horror adventure inspired by the cosmic dread of
H.P. Lovecraft's Mythos. You play an investigator pulled into events that
were never meant to be understood — exploring shadowed locations, gathering
fragments of forbidden knowledge, and trying to survive with your mind
(mostly) intact.

No graphics, no sound — just prose, choices, and the growing sense that you
already know too much.

## Scenarios

- **The Manor** (`--scenario manor`) — an old, original estate, 13 rooms
  and 8 clues (only 6 needed to win), with a 150-point sanity pool,
  a safe room to rest in, and a rare curative item.
- **Hollow Tide** (`--scenario hollow_tide`) — Eldritch's Innsmouth: a
  tide-locked fishing town run from the inside by a congregation that's
  stopped pretending to worship anything human. Deliberately the bigger,
  looser scenario now — 22 rooms across five loose clusters (waterfront,
  town core, industrial, hill/estate, cemetery), 4 locked doors, 11 clues
  (7 needed), 2 safe rooms, 2 curatives, and its own reskinned threat
  ("the shambler," with a riskier public street to match).
- **The Reagent** (`--scenario reanimator`) — inspired by Lovecraft's
  "Herbert West–Reanimator" (public domain, 1922). The player is an
  outside detective investigating Dr. West's disappearance, not his
  complicit assistant. 12 rooms, 7 clues (6 needed), 2 locked doors,
  a 150-point sanity pool, and its own threat: the reanimated dead
  themselves, stiff-moving and unreliable-sensed.

Every scenario uses the exact same engine, unmodified — only the data
files differ, right down to how their stalking threats look, feel, and
are paced.

## Creating Your Own Scenario

Copy `data/_template/` (a minimal, fully working 2-room example with
every field commented, including all the scaling/theming ones below)
to a new folder under `data/`, edit the four files, then run it:

```bash
cp -r data/_template data/my_scenario
python main.py --scenario my_scenario
```

Or copy `data/manor/` or `data/hollow_tide/` instead if you'd rather
start from something bigger. Every scenario needs the same four files:

| File            | Contents |
|-------------------|------------|
| `manifest.yaml`     | `title`, `start_room` (required); `description`, `intro`, and the scaling/theming fields below (all optional) |
| `rooms.yaml`          | Each room: `name`, `description_variants` (list — one picked at random), `exits`; optional `safe`/`rest_amount`/`rest_text`, `risk_multiplier`, `scenery` (noun → text, examinable) |
| `items.yaml`            | Each item: `name`, `valid_rooms` (list — one picked at random); optional `description` (shown by `examine`), `on_take_sanity`, `on_take_text`, `is_clue`, `on_use_sanity`, `on_use_text` |
| `events.yaml`             | List of random events: `id`, `rooms`, `chance`, `text`; optional `sanity_effect`, `repeat` (default false — a one-shot event; `true` lets it recur, for ambient flavor) |

Exits come in a few shapes: a normal `{target: room_id}`, a locked one
(`locked: true`, `unlock_item`, `locked_text`, `unlock_text`), a knowledge-
gated one (`requires_clues`), the win exit (`requires_all_clues: true`, no
target — see `clues_required` below), or a tiered `finale` (see *Chapters*
below). If any item has `is_clue: true`, some exit needs
`requires_all_clues: true` (or a `finale`), and vice versa — the game won't start if
that's out of balance.

**Scaling a bigger scenario** — optional `manifest.yaml` fields:
- `max_sanity` — the sanity pool size (default 100). Raise this for a
  scenario with more clues/rooms so the math still works out.
- `clues_required` — how many `is_clue` items are needed to win, if
  fewer than the total (a forgiving, replayable threshold rather than
  requiring every single one).
- `sanity_tier_thresholds` — override where Lucid/Uneasy/Fraying begin
  (as a % of `max_sanity`; Broken is always the floor).

**Auto-balancing** (`game/balance.py`) — so a longer scenario doesn't
end up harsher just for being longer, two multipliers are computed
automatically at load time, relative to a 7-room / 8-sanity-cost
baseline: `dread_scale` (per-turn chance the presence advances; more
rooms means more turns, so it drops) and `sanity_scale` (applied to every
`on_take_sanity` / `sanity_effect`; more costly content means each cost
shrinks). Restoratives (`on_use_sanity`) and `rest_amount` are never
scaled. Both are clamped to 0.35-2.5, and note it works in both
directions: a *small* scenario is scaled up (a 2-room one gets the full
2.5x). Set either in `manifest.yaml` to override; `1.0` means "exactly
as authored". Manor, Hollow Tide and The Reagent were hand-tuned and are
pinned to `1.0` — delete those lines after extending one to let it
auto-scale.

**Chapters, knowledge gates & tiered endings** — for a long, multi-part
story (think *The Call of Cthulhu*: several places, then a finale).

- `chapters:` in the manifest defines them: `{id: {title, intro, threat}}`.
  A room opts in with `chapter: <id>`; entering a room in a new chapter
  prints its banner (title + intro), and `status` shows the current one.
  "One-way" travel is just leaving out the return exit. An exit's
  `travel_text` is printed as you cross it (a train pulling out, a ship
  putting to sea).
- `requires_clues: N` on a normal exit (with a `target`) is a knowledge
  gate: it shows as `(not ready)` and refuses you, using `locked_text`,
  until you hold N clues. It isn't an escape route from the presence.
- `finale:` on an exit (no `target`) is a tiered ending: a list of
  `{min_clues, text, result: win|lose}` checked top to bottom, highest
  `min_clues` first, the last entry having no `min_clues` as the fallback.
  So "seal it fully / seal it at a cost / fail" is one action whose result
  depends on how much you learned. Existing `requires_all_clues` exits keep
  working unchanged.
- A chapter's `threat:` block overrides the scenario-wide one for rooms in
  that chapter, merging over it, so a chapter can change just the flavor
  text, or the pacing too.

**Recovery** — a room with `safe: true` can be rested in (`rest`/`recover`,
restores `rest_amount`, default 15); an item with `on_use_sanity` is a
rare, single-use restorative via `use <item>`.

**Re-skinning the threat** — every scenario shares the same underlying
stalking-presence mechanic (dread builds, it manifests, flee or hide or
you're caught), but a `threat:` block in the manifest can retune its
pacing (`threshold`, `chance_by_tier`) and completely rewrite its flavor
text (`manifest_text`, `caught_text`, `evade_text`, `hide_text`) — see
Hollow Tide's "shambler" for a from-scratch example. A room's
`risk_multiplier` makes it riskier than the rest of the scenario (a
public street, say) without touching any code. `win_text` and
`broken_text` on the manifest override the ending text too.

**The necronomicon** — every scenario gets one automatically; you don't
need to add it to `items.yaml` yourself. If you want scenario-specific
flavor text (see Hollow Tide's), just define an item with the id
`necronomicon` and yours is used instead of the generic default — the
mechanic itself (safe to `examine`, costly to `use`) is engine-enforced
either way, so you can't accidentally change what reading it actually does.

If anything's wrong — a typo'd room name, a locked door with no key,
a clue with nowhere to lead, an out-of-range chance — the game refuses
to start and tells you exactly what's broken, rather than crashing
mid-playthrough.

## Features

- **Room-by-room exploration** via classic text-adventure commands ✅
- **A scenario selection menu** — running with no `--scenario` flag lists
  every scenario found under `data/` plus a Random option, resolved
  through the same seeded RNG as the rest of the run ✅
- **Exits remember what you've found** — a visited room's name shows up
  in its exit listing; anywhere you haven't been just says "Undiscovered" ✅
- **Deep sanity system** — as sanity drops, room narration becomes
  unreliable (intrusive asides, stuttering text), and it also raises the
  odds of the stalking threat finding you ✅
- **Investigation-first survival** — no combat; an unseen threat stalks
  each scenario, and getting caught by it or losing your sanity entirely
  both end the run ✅
- **Randomized per playthrough** — item locations, room description
  flavor, and which random events fire are all reshuffled by a seeded RNG
  each run (`--seed` to reproduce a specific one) ✅
- **A real win condition** — piece together enough of a scenario's story
  via its scattered clues, then reach the exit ✅
- **Inventory, locked doors, and a limited recovery system** — safe rooms
  and rare curative items, so bigger scenarios stay winnable ✅
- **A universal risk/reward artifact** — the necronomicon is present in
  every scenario (auto-added if a scenario doesn't define its own),
  and can be safely previewed via `examine` before the player decides
  whether to actually `use` (read) it: +2 clues, at the cost of half
  their current sanity and all future sanity recovery that run ✅
- **Fully re-skinnable per scenario** — sanity pool size, clue threshold,
  and the stalking threat's pacing/flavor text are all scenario-configurable,
  not hardcoded ✅
- **Save/load** — `save [name]` / `load [name]` at any time (even mid-encounter),
  or resume from the command line with `--load [name]`. Saves keep the exact
  world, your progress, and the RNG state, and survive prose edits to a scenario ✅
- More puzzles, additional endings — planned
- **Optional terminal styling** — color and light ASCII art — not started

## Tech Stack

- **Python 3.10+**
- **PyYAML** — the only dependency. Adventure content (rooms, items,
  events) lives in hand-authored YAML data files rather than Python code.

## Project Structure

```
eldritch/
├── main.py                # Entry point — loads a scenario, runs the game loop
├── game/                  # The engine - generic, has no story content in it
│   ├── __init__.py
│   ├── content_loader.py   # Loads + validates a scenario's YAML files
│   ├── player.py            # Player state: location, sanity, inventory
│   ├── parser.py              # Command input parsing
│   ├── sanity.py               # Sanity tiers & narration distortion
│   ├── entities.py              # The stalking presence (dread system)
│   ├── world.py                  # Resolves a scenario's templates into one playthrough
│   ├── save_load.py               # Save/load: snapshots of a playthrough's changing state
│   ├── balance.py                 # Auto-scales dread frequency & sanity costs to scenario size
│   └── rng.py                     # Seeded RNG for reproducible randomness
├── data/                  # Adventure content lives here, not in code
│   ├── manor/                # Scenario 1: "The Manor"
│   │   ├── manifest.yaml     # Title, intro text, starting room
│   │   ├── rooms.yaml         # Rooms: description variants, exits
│   │   ├── items.yaml          # Items: placement pools, sanity effects
│   │   └── events.yaml          # Random events
│   ├── hollow_tide/          # Scenario 2: "Hollow Tide" - Eldritch's Innsmouth
│   │   └── (same four files, 22 rooms)
│   ├── reanimator/           # Scenario 3: "The Reagent" - a Herbert West-inspired case
│   │   └── (same four files, 12 rooms)
│   └── _template/            # Minimal, fully working, heavily-commented
│       └── (same four files)   # starting point for a new scenario
├── tests/
│   └── test_engine.py      # Parser, sanity, loader/validator, world-gen, win/lose
├── requirements.txt        # PyYAML
└── README.md
```

Adding a new adventure means adding a new folder under `data/` with those
same four files — the engine itself doesn't need to change. Run one with
`python main.py --scenario <folder-name>`.

Saves are written to a `saves/` folder next to `main.py` (or next to the exe).

## Getting Started

### Requirements
- Python 3.10 or later

### Windows release (no Python needed)

Download `Eldritch-<version>-windows.zip` from the
[Releases page](https://github.com/PNGuinn-sys/Eldritch/releases), unzip
it, and double-click `Eldritch.exe`. Keep the `data/` folder next to the
exe: that's where scenarios are loaded from, so you can add your own
(see *Creating Your Own Scenario*) or edit existing ones with no
rebuild. If `data/` is missing, the exe falls back to the copies bundled
inside it. Windows SmartScreen or antivirus may warn about the exe
because it isn't code-signed; the release notes list its SHA-256 so you
can verify the download.

### Installation
```bash
git clone https://github.com/PNGuinn-sys/Eldritch.git
cd Eldritch
pip install -r requirements.txt   # installs PyYAML
```

### Running the Game
```bash
python main.py                                  # shows a scenario menu (see below)
python main.py --scenario manor                  # skip the menu, load a specific one
python main.py --scenario hollow_tide            # the other scenario, same way
python main.py --seed 42 --show-seed            # a reproducible run, for testing
python main.py --load                            # resume your 'quicksave' (or --load <name>)
```

Running with no `--scenario` shows a menu of every scenario found under
`data/` (by title, read from each one's manifest), plus a trailing
"Random" option:

```
Available scenarios:
  1. Hollow Tide
  2. The Manor
  3. The Reagent
  4. Random

Choose a scenario (number):
```

`_template` is intentionally left out of this list (it's a starting
point for authors, not something to play) but is still directly
playable via `--scenario _template`. Random is resolved through the
same seeded RNG as everything else, so `--seed 42` + Random always
picks the same scenario on a given seed, exactly like any other choice
that seed makes.

If a scenario's data files have a mistake in them (a typo'd room name, a
locked door with no key, etc.), the game will refuse to start and print
exactly what's wrong, rather than crashing mid-playthrough.

### Running the Tests
```bash
python tests/test_engine.py
```

## How to Play

| Command              | Effect                                    |
|-----------------------|--------------------------------------------|
| `look` / `l`            | Describe current surroundings             |
| `examine <thing>` / `x`  | Look closer at an item or room scenery    |
| `go <direction>` / `n`,`s`,`e`,`w`,`u`,`d` | Move (also `in`/`out`) |
| `take <item>`             | Pick up an item                           |
| `drop <item>`               | Drop an item                              |
| `use <item>`                  | Use an item (e.g. a key on a locked door, or a curative) |
| `inventory` / `i`               | List carried items                        |
| `status` / `stats`                | Location, sanity, inventory, clue & room progress |
| `hide` / `wait`                     | Evade the threat when it manifests        |
| `rest` / `recover`                    | Recover sanity, in a room marked safe     |
| `save [name]` / `load [name]`         | Save or restore your game (default slot `quicksave`); takes no turn |
| `quit`                                  | Exit the game                         |

**Winning:** collect enough clues to piece the scenario's story together
(`status` shows your progress, e.g. "6 needed to leave"), then reach its
exit — in the manor, that's going `out` through the front door. The
necronomicon counts as +2 clues if you're willing to pay for reading it.
**Losing:** your sanity reaches 0, or the presence catches you when it
manifests and your next move isn't fleeing or hiding.

## Roadmap

- [x] Core game loop & command parser
- [x] World map & room system (randomized per playthrough)
- [x] Sanity mechanic (narration distortion + gameplay consequence via the presence)
- [x] Inventory & a first puzzle (locked door)
- [x] First playable chapter — win and lose both work end to end
- [x] Content split into data files — adventures are now YAML, not Python;
      engine validates them at startup
- [x] A second scenario ("Hollow Tide") — confirms the engine, presence,
      and win/lose logic all work unmodified against different content
- [x] Scaling knobs — sanity pool size, partial clue thresholds, and a
      limited recovery system (safe rooms, rare curative items) so bigger
      scenarios stay winnable rather than just harder
- [x] The stalking presence is fully scenario-configurable — pacing,
      per-room risk, and flavor text can all be overridden, so each
      scenario's threat can feel genuinely distinct
- [x] Hollow Tide expanded drastically (7 → 22 rooms) as a real stress
      test of the data-driven split, and committed to an explicit
      identity — Eldritch's Innsmouth — separate from any future,
      differently-set cult scenario
- [x] Two more generic engine primitives, motivated by that expansion:
      `examine <thing>` (item descriptions + room scenery text, no
      new items required) and repeatable ambient events (vs. one-shot
      story beats)
- [x] Save/load system
- [ ] More rooms, more clues, more puzzles in either scenario
- [ ] Additional/varied endings beyond win/caught/broken
- [ ] Polish — styling, pacing

## Design Notes

Decisions locked in so far:

- **Setting:** Original/timeless — not tied to a specific real-world era.
  We're free to invent our own locations, factions, and fragments of
  forbidden lore rather than reusing Arkham/Innsmouth-style canon.
- **Sanity mechanic:** Deep. Sanity isn't just a number in a status bar —
  as it drops, the narration itself becomes unreliable. Room descriptions
  may shift or contradict themselves, exits may mislead, and the player
  may not always be able to trust what the game tells them.
- **Danger/combat:** Investigation-focused. There's no combat system —
  threats are survived by avoiding, hiding from, or escaping them. Tension
  comes from evasion, not fighting.
- **The threat:** an unseen presence, not a monster you see coming. Dread
  builds quietly (faster at low sanity) and manifests as a sudden "you are
  not alone" moment — your very next action has to be fleeing or hiding.
- **The goal:** piece together the manor's story via scattered clues, then
  leave through a front door that was locked until you understood enough.

Still open:
- Story premise / inciting incident
- Number & structure of chapters or acts
- How many distinct endings, and what determines them
- Tone calibration (slow-burn dread vs. more frequent scares)

## License

TBD — MIT suggested for a personal/open project.
