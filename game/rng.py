"""
Central RNG for Eldritch.

Every playthrough gets its own seed - random by default, so the world
and its events differ session to session. A specific seed can be pinned
(via --seed on the command line) to reproduce an exact run for debugging.
"""

import random


def make_rng(seed=None):
    """Return (rng, seed_used).

    If seed is None, a fresh random seed is generated and returned
    alongside the RNG so it can be logged/reproduced later.
    """
    if seed is None:
        seed = random.SystemRandom().randrange(0, 2**32 - 1)
    return random.Random(seed), seed
