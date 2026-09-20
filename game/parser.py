"""
Command parser for Eldritch.

Converts raw player input into a structured Command the game loop can
act on. Kept deliberately simple: verb + optional direction/target.
As the game grows, this can be extended with prepositions
("use key on door"), multi-word verbs, etc.
"""

from dataclasses import dataclass
from typing import Optional


DIRECTIONS = {
    "north": "north", "n": "north",
    "south": "south", "s": "south",
    "east": "east", "e": "east",
    "west": "west", "w": "west",
    "up": "up", "u": "up",
    "down": "down", "d": "down",
    "in": "in", "enter": "in",
    "out": "out",
}

VERB_ALIASES = {
    "look": "look", "l": "look",
    "examine": "examine", "x": "examine", "inspect": "examine", "read": "examine",
    "go": "go", "move": "go", "walk": "go",
    "take": "take", "get": "take", "grab": "take", "pick": "take", "pickup": "take",
    "drop": "drop", "discard": "drop",
    "inventory": "inventory", "inv": "inventory", "i": "inventory",
    "use": "use", "apply": "use", "open": "use",
    "hide": "hide", "wait": "hide", "crouch": "hide",
    "rest": "rest", "recover": "rest",
    "save": "save",
    "load": "load",
    "status": "status", "stats": "status", "sanity": "status", "diagnose": "status",
    "help": "help", "?": "help",
    "quit": "quit", "q": "quit",
}


@dataclass
class Command:
    verb: str
    direction: Optional[str] = None
    target: Optional[str] = None
    raw: str = ""


def parse(raw_input: str) -> Command:
    """Parse a raw line of player input into a Command."""
    raw = raw_input.strip().lower()
    if not raw:
        return Command(verb="empty", raw=raw_input)

    words = raw.split()
    first = words[0]

    # A bare direction typed alone, e.g. "north" or "n"
    if first in DIRECTIONS and len(words) == 1:
        return Command(verb="go", direction=DIRECTIONS[first], raw=raw_input)

    if first not in VERB_ALIASES:
        return Command(verb="unknown", raw=raw_input)

    verb = VERB_ALIASES[first]
    rest = words[1:]

    if verb == "go":
        if rest and rest[0] in DIRECTIONS:
            return Command(verb="go", direction=DIRECTIONS[rest[0]], raw=raw_input)
        return Command(verb="go", direction=None, raw=raw_input)

    target = " ".join(rest) if rest else None
    return Command(verb=verb, target=target, raw=raw_input)
