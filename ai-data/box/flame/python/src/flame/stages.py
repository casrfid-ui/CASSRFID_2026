"""The stages of the flame processing as small pure functions."""


def polarity(raw, active_low):
    """Stage 1. Reads to booleans: True = flame seen."""
    return [(v == 0) if active_low else (v != 0) for v in raw]


def vote(active, vote_ratio):
    """Stage 2. Burst is positive when the positives reach `vote_ratio` of the burst."""
    return sum(active) >= vote_ratio * len(active)


def transitions(active):
    """Stage 3. Number of changes between consecutive reads."""
    return sum(1 for a, b in zip(active, active[1:]) if a != b)
