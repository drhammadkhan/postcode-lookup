"""Helpers shared by the folium-based map generators."""

import random


def make_folium_ids_deterministic(seed=0):
    """Make folium/branca element ids reproducible.

    branca names every map element with a random id, so regenerating an
    unchanged map rewrites hundreds of lines in the committed HTML. Seeding
    the id generator keeps `git diff` limited to real changes.
    Call this once, before any folium objects are created.
    """
    import branca.element

    rng = random.Random(seed)
    branca.element.urandom = lambda n: rng.randbytes(n)
