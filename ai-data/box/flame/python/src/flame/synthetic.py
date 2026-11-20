"""Simulated bursts for studying the rules. EVERYTHING HERE IS A MODEL, not a measurement of the KY-026:
no recording of the module exists in the project. Parameters are assumptions, named as such in the notebook."""
import random


def clean_burst(n, glitch_p, rng):
    """Dark scene, each read wrongly positive with probability `glitch_p` (independent). Active-low raw reads."""
    return [0 if rng.random() < glitch_p else 1 for _ in range(n)]


def steady_burst(n):
    """Sunlight or a reflection lighting the module for the whole burst: every read positive."""
    return [0] * n


def flame_burst(n, rng, duty=0.8, flip=0.3):
    """Flickering flame: two-state chain, positive `duty` of the time, state changes with probability `flip` per read."""
    state = rng.random() < duty
    out = []
    for _ in range(n):
        out.append(0 if state else 1)
        if rng.random() < flip:
            state = rng.random() < duty
    return out
